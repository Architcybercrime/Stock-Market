"""Fully-local paper broker.

Use when you cannot or do not want to sign up for an external broker. Combines:

- yfinance for current prices (free, no API key)
- A JSON state file for portfolio persistence (cash, positions, fills)
- The same SlippageModel and CostModel as the backtester, so simulated fills
  are comparable to backtest results

State file layout (`paper_state.json`):

    {
      "schema_version": 1,
      "cash": "100000.00",
      "initial_capital": "100000.00",
      "positions": { "AAPL": "10", "MSFT": "5" },
      "avg_costs": { "AAPL": "182.34", "MSFT": "421.10" },
      "realized_pnl": "120.50",
      "orders": [ {...}, ... ],
      "fills":  [ {...}, ... ],
      "equity_history": [ ["2026-05-22T20:00:00+00:00", "100120.50"], ... ],
      "updated_at": "2026-05-22T20:30:00+00:00"
    }

Idempotent on client_order_id: re-submitting the same id is a no-op.

Caller is expected to provide a price source. We accept either a callable
`(symbol) -> float` or any object with a `latest_close(symbol)` method.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Protocol

from libs.common.logging import get_logger
from libs.common.types import Fill, Order, OrderSide, OrderStatus
from services.backtest.costs import CostModel, SlippageModel
from services.execution.brokers.base import Broker, BrokerError

log = get_logger(__name__)

SCHEMA_VERSION = 1


class _PriceFetcher(Protocol):
    def latest_close(self, symbol: str) -> float | None: ...


PriceSource = Callable[[str], float] | _PriceFetcher


class LocalPaperBroker(Broker):
    """Fully-local paper broker. No external broker account needed."""

    name = "local_paper"
    is_paper = True

    def __init__(
        self,
        state_path: Path,
        price_source: PriceSource,
        *,
        initial_cash: float = 100_000.0,
        cost_model: CostModel | None = None,
        slippage_model: SlippageModel | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        self._price_source = price_source
        self.cost_model = cost_model or CostModel()
        self.slippage_model = slippage_model or SlippageModel()
        self.initial_cash = Decimal(str(initial_cash))
        self._load_or_init()

    # ------------------------------------------------------------------ state

    def _load_or_init(self) -> None:
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text())
            self.cash = Decimal(data.get("cash", str(self.initial_cash)))
            self.positions = {s: Decimal(q) for s, q in data.get("positions", {}).items()}
            self.avg_costs = {s: Decimal(c) for s, c in data.get("avg_costs", {}).items()}
            self.realized_pnl = Decimal(data.get("realized_pnl", "0"))
            self._orders_raw: list[dict] = data.get("orders", [])
            self._fills_raw: list[dict] = data.get("fills", [])
            self.equity_history: list[tuple[str, str]] = data.get("equity_history", [])
            self.initial_capital = Decimal(data.get("initial_capital", str(self.initial_cash)))
            log.info(
                "local_paper.state_loaded",
                path=str(self.state_path),
                cash=str(self.cash),
                positions=len(self.positions),
            )
        else:
            self.cash = self.initial_cash
            self.initial_capital = self.initial_cash
            self.positions = {}
            self.avg_costs = {}
            self.realized_pnl = Decimal(0)
            self._orders_raw = []
            self._fills_raw = []
            self.equity_history = []
            log.info("local_paper.state_initialized", initial_cash=str(self.initial_cash))

        # Client-order-id index for idempotency
        self._client_index: dict[str, int] = {
            o["client_order_id"]: i for i, o in enumerate(self._orders_raw)
            if "client_order_id" in o
        }

        # Persist immediately so the file exists even before any orders fill.
        # Downstream tooling (show_portfolio, dashboard, audit commit step) can
        # then always assume the state file is present.
        if not self.state_path.exists():
            self._save()

    def _save(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "cash": str(self.cash),
            "initial_capital": str(self.initial_capital),
            "positions": {s: str(q) for s, q in self.positions.items()},
            "avg_costs": {s: str(c) for s, c in self.avg_costs.items()},
            "realized_pnl": str(self.realized_pnl),
            # Bound history so the state file does not grow without limit
            "orders": self._orders_raw[-2000:],
            "fills": self._fills_raw[-2000:],
            "equity_history": self.equity_history[-2000:],
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload, indent=2))

    # ------------------------------------------------------------------ prices

    def _get_price(self, symbol: str) -> float:
        ps = self._price_source
        try:
            if callable(ps):
                price = ps(symbol)
            else:
                price = ps.latest_close(symbol)
        except Exception as exc:
            raise BrokerError(f"price fetch failed for {symbol}: {exc}") from exc
        if price is None or not (price == price) or price <= 0:
            raise BrokerError(f"invalid price for {symbol}: {price}")
        return float(price)

    # ------------------------------------------------------------------ orders

    def submit(self, order: Order) -> Order:
        # Idempotency: re-submit of same client_order_id returns the stored result.
        if order.client_order_id in self._client_index:
            stored = self._orders_raw[self._client_index[order.client_order_id]]
            order.status = OrderStatus(stored["status"])
            order.filled_qty = Decimal(stored.get("filled_qty", "0"))
            if stored.get("avg_fill_price"):
                order.avg_fill_price = Decimal(stored["avg_fill_price"])
            return order

        # Price + slippage + fee
        try:
            ref_price = self._get_price(order.symbol)
        except BrokerError as exc:
            order.status = OrderStatus.REJECTED
            order.reject_reason = str(exc)
            self._record_order(order, fee=Decimal(0))
            return order

        is_buy = order.side == OrderSide.BUY
        fill_price = self.slippage_model.apply(ref_price, float(order.qty), adv=None, is_buy=is_buy)
        notional = float(order.qty) * fill_price
        fee = Decimal(str(self.cost_model.fee(notional, is_sell=not is_buy)))

        # Cash check (long-only protection)
        if is_buy and self.cash < Decimal(str(notional)) + fee:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"insufficient_cash: have={self.cash} need={notional + float(fee):.2f}"
            self._record_order(order, fee=fee)
            log.warning("local_paper.reject", reason=order.reject_reason, order_id=order.id)
            return order

        if not is_buy:
            held = self.positions.get(order.symbol, Decimal(0))
            if held < order.qty:
                order.status = OrderStatus.REJECTED
                order.reject_reason = f"insufficient_position: have={held} need={order.qty}"
                self._record_order(order, fee=fee)
                log.warning("local_paper.reject", reason=order.reject_reason, order_id=order.id)
                return order

        # Apply the fill
        fill_price_d = Decimal(str(fill_price))
        signed_qty = order.qty if is_buy else -order.qty
        self.cash -= signed_qty * fill_price_d + fee

        prior_qty = self.positions.get(order.symbol, Decimal(0))
        new_qty = prior_qty + signed_qty

        if is_buy:
            if prior_qty == 0:
                self.avg_costs[order.symbol] = fill_price_d
            else:
                prior_cost = self.avg_costs.get(order.symbol, fill_price_d)
                # Weighted average for adds to existing long
                self.avg_costs[order.symbol] = (
                    (prior_cost * prior_qty + fill_price_d * order.qty) / new_qty
                )
        else:
            # Realize P&L on the sold qty using FIFO simplification (single avg_cost)
            entry_cost = self.avg_costs.get(order.symbol, fill_price_d)
            self.realized_pnl += (fill_price_d - entry_cost) * order.qty - fee

        if new_qty == 0:
            self.positions.pop(order.symbol, None)
            self.avg_costs.pop(order.symbol, None)
        else:
            self.positions[order.symbol] = new_qty

        order.status = OrderStatus.FILLED
        order.filled_qty = order.qty
        order.avg_fill_price = fill_price_d

        fill = Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=fill_price_d,
            fee=fee,
            venue=self.name,
            ts=datetime.now(UTC),
        )
        self._fills_raw.append(self._fill_to_dict(fill))
        self._record_order(order, fee=fee)
        self._update_equity_history()
        self._save()

        log.info(
            "local_paper.fill",
            symbol=order.symbol,
            side=order.side.value,
            qty=str(order.qty),
            price=fill_price,
            fee=str(fee),
            cash_after=str(self.cash),
        )
        return order

    def cancel(self, broker_order_id: str) -> None:
        # All LocalPaperBroker submissions fill immediately, so cancel is a no-op
        # for filled orders. For rejected ones the status is already terminal.
        return

    def get_order(self, broker_order_id: str) -> Order:
        for stored in self._orders_raw:
            if stored.get("id") == broker_order_id:
                return _order_from_dict(stored)
        raise BrokerError(f"unknown order id: {broker_order_id}")

    def list_open_orders(self) -> list[Order]:
        return []  # immediate-fill model — no open orders ever

    def list_positions(self) -> dict[str, Decimal]:
        return {sym: qty for sym, qty in self.positions.items() if qty != 0}

    def poll_fills(self, since: str | None = None) -> Iterable[Fill]:
        if since is None:
            return [_fill_from_dict(f) for f in self._fills_raw]
        cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
        return [
            _fill_from_dict(f) for f in self._fills_raw
            if datetime.fromisoformat(f["ts"]) > cutoff
        ]

    # ------------------------------------------------------------------ daemon hooks

    def get_account(self) -> dict[str, Any]:
        """Daemon calls this to learn NAV, cash, buying power."""
        equity = self.cash
        for sym, qty in self.positions.items():
            try:
                price = Decimal(str(self._get_price(sym)))
            except BrokerError:
                price = self.avg_costs.get(sym, Decimal(0))
            equity += qty * price
        return {
            "equity": float(equity),
            "cash": float(self.cash),
            "buying_power": float(self.cash),
            "pattern_day_trader": False,
        }

    # ------------------------------------------------------------------ helpers

    def _record_order(self, order: Order, fee: Decimal) -> None:
        d = {
            "id": order.id,
            "client_order_id": order.client_order_id,
            "strategy": order.strategy,
            "symbol": order.symbol,
            "side": order.side.value,
            "qty": str(order.qty),
            "type": order.type.value,
            "limit_price": str(order.limit_price) if order.limit_price else None,
            "tif": order.tif,
            "status": order.status.value,
            "filled_qty": str(order.filled_qty),
            "avg_fill_price": str(order.avg_fill_price) if order.avg_fill_price else None,
            "fee": str(fee),
            "reject_reason": order.reject_reason,
            "created_at": order.created_at.isoformat(),
        }
        self._orders_raw.append(d)
        self._client_index[order.client_order_id] = len(self._orders_raw) - 1

    def _fill_to_dict(self, fill: Fill) -> dict:
        return {
            "id": fill.id,
            "order_id": fill.order_id,
            "symbol": fill.symbol,
            "side": fill.side.value,
            "qty": str(fill.qty),
            "price": str(fill.price),
            "fee": str(fill.fee),
            "venue": fill.venue,
            "ts": fill.ts.isoformat(),
        }

    def _update_equity_history(self) -> None:
        acc = self.get_account()
        self.equity_history.append((datetime.now(UTC).isoformat(), str(acc["equity"])))


# Module-level helpers --------------------------------------------------------

def _order_from_dict(d: dict) -> Order:
    from libs.common.types import OrderType

    return Order(
        id=d["id"],
        client_order_id=d["client_order_id"],
        strategy=d["strategy"],
        symbol=d["symbol"],
        side=OrderSide(d["side"]),
        qty=Decimal(d["qty"]),
        type=OrderType(d["type"]),
        limit_price=Decimal(d["limit_price"]) if d.get("limit_price") else None,
        tif=d.get("tif", "DAY"),
        status=OrderStatus(d["status"]),
        filled_qty=Decimal(d.get("filled_qty", "0")),
        avg_fill_price=Decimal(d["avg_fill_price"]) if d.get("avg_fill_price") else None,
        reject_reason=d.get("reject_reason"),
        created_at=datetime.fromisoformat(d["created_at"]),
    )


def _fill_from_dict(d: dict) -> Fill:
    return Fill(
        id=d["id"],
        order_id=d["order_id"],
        symbol=d["symbol"],
        side=OrderSide(d["side"]),
        qty=Decimal(d["qty"]),
        price=Decimal(d["price"]),
        fee=Decimal(d["fee"]),
        venue=d.get("venue", "local_paper"),
        ts=datetime.fromisoformat(d["ts"]),
    )
