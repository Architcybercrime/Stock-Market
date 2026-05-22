"""Trading daemon runner.

One run() cycle:
1. Snapshot account from broker (cash, positions, equity).
2. Pull recent bars for each symbol in the universe.
3. Evaluate each signal generator against each symbol.
4. Aggregate to target weights and delta orders.
5. Each delta order goes through OMS (which runs pre-trade risk checks).
6. Log decisions + orders + audit row.

The daemon is intentionally non-magical: it logs everything it decides
*before* it acts, so even if something goes wrong you can read the log
and reconstruct what it thought.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from libs.common.config import settings
from libs.common.logging import get_logger
from libs.common.types import Order, OrderSide
from services.daemon.aggregator import AggregatorResult, SignalAggregator
from services.daemon.profiles import RiskProfile
from services.daemon.strategies import (
    MeanReversionSignal,
    MLSignal,
    MomentumSignal,
    SignalGenerator,
)
from services.execution.brokers.base import Broker
from services.execution.oms import OMS
from services.ingestion.sources.base import DataSource
from services.risk.checks import PortfolioState
from services.risk.circuit_breaker import CircuitBreaker
from services.risk.kill_switch import KillSwitch
from services.risk.limits import RiskLimitsConfig

log = get_logger(__name__)


@dataclass
class DaemonRunReport:
    """What happened in one daemon run. Used by the scheduler + audit log."""

    ts: datetime
    profile_name: str
    nav: float
    cash: float
    n_positions_before: int
    n_signals_evaluated: int
    n_selected: int
    n_orders_attempted: int
    n_orders_accepted: int
    n_orders_rejected: int
    aggregator_result: AggregatorResult | None
    error: str | None = None


class TradingDaemon:
    def __init__(
        self,
        broker: Broker,
        data_source: DataSource,
        profile: RiskProfile,
        universe: list[str],
        signal_generators: list[SignalGenerator] | None = None,
        history_bars: int = 260,
        timeframe: str = "1d",
    ) -> None:
        self.broker = broker
        self.data_source = data_source
        self.profile = profile
        self.universe = universe
        self.signal_generators = signal_generators or [
            MomentumSignal(),
            MeanReversionSignal(),
            MLSignal(),
        ]
        self.history_bars = history_bars
        self.timeframe = timeframe
        self.aggregator = SignalAggregator(profile)

        # Risk infrastructure
        self.kill_switch = KillSwitch(Path(settings.data_root) / "KILL_SWITCH")
        self.circuit_breaker = CircuitBreaker(
            max_daily_loss_pct=settings.risk.max_daily_loss_pct,
            max_drawdown_pct=settings.risk.max_drawdown_pct,
        )
        limits_cfg = RiskLimitsConfig(
            max_daily_loss_pct=settings.risk.max_daily_loss_pct,
            max_drawdown_pct=settings.risk.max_drawdown_pct,
            max_position_pct=profile.max_position_pct,
            max_sector_pct=settings.risk.max_sector_pct,
            max_leverage=settings.risk.max_leverage,
            min_cash_buffer_pct=max(0.0, 1.0 - profile.target_invested_pct - 0.02),
            max_orders_per_minute=settings.risk.max_orders_per_minute,
            max_order_notional_pct=profile.max_position_pct,
        )
        self.oms = OMS(
            broker=broker,
            limits=limits_cfg,
            kill_switch=self.kill_switch,
            circuit_breaker=self.circuit_breaker,
        )

    # ------------------------------------------------------------------ pieces

    def _account_snapshot(self) -> tuple[float, float, dict[str, float]]:
        if hasattr(self.broker, "get_account"):
            acc = self.broker.get_account()
            equity = float(acc["equity"])
            cash = float(acc["cash"])
        else:
            equity = 100_000.0
            cash = 100_000.0
        positions = {sym: float(qty) for sym, qty in self.broker.list_positions().items()}
        return equity, cash, positions

    def _pull_history(self, end: datetime) -> dict[str, pd.DataFrame]:
        from datetime import timedelta

        # Window size scales with the chosen timeframe so we get roughly
        # `history_bars` bars per symbol. Buffered for weekends/holidays.
        days_per_bar = {
            "1d": 1.6,        # ~1 bar / day + weekend buffer
            "1h": 1 / 4.5,    # ~6.5 trading hours per day; allow buffer
            "30m": 1 / 9.0,
            "15m": 1 / 18.0,
        }.get(self.timeframe, 1.6)
        start = end - timedelta(days=max(7, int(self.history_bars * days_per_bar)))
        out: dict[str, pd.DataFrame] = {}
        for sym in self.universe:
            try:
                df = self.data_source.fetch_bars(sym, start, end, self.timeframe)
            except Exception as exc:
                log.warning("daemon.fetch_failed", symbol=sym, error=str(exc))
                continue
            if df is None or df.empty:
                continue
            out[sym] = df
        return out

    def _evaluate_signals(
        self, histories: dict[str, pd.DataFrame]
    ):
        from services.daemon.strategies.base import StrategySignal

        all_signals: dict[str, list[StrategySignal]] = {}
        for sym, hist in histories.items():
            sigs: list[StrategySignal] = []
            for gen in self.signal_generators:
                try:
                    sig = gen.evaluate(sym, hist)
                except Exception as exc:
                    log.error("daemon.signal_error", strategy=gen.name, symbol=sym, error=str(exc))
                    continue
                sigs.append(sig)
                log.info(
                    "daemon.signal",
                    strategy=gen.name,
                    symbol=sym,
                    score=round(sig.score, 4),
                    confidence=round(sig.confidence, 3),
                    rationale=sig.rationale,
                )
            all_signals[sym] = sigs
        return all_signals

    def _submit_order(
        self,
        target_order,
        portfolio_state: PortfolioState,
        last_prices: dict[str, float],
    ) -> Order | None:
        from libs.common.types import Order, OrderType

        side = OrderSide.BUY if target_order.side == "buy" else OrderSide.SELL
        order = Order(
            strategy="daemon",
            symbol=target_order.symbol,
            side=side,
            qty=Decimal(str(int(target_order.qty))),
            type=OrderType.MARKET,
            created_at=datetime.now(UTC),
        )
        ref_price = last_prices.get(target_order.symbol)
        if ref_price is None or ref_price <= 0:
            log.warning("daemon.no_price_for_order", symbol=target_order.symbol)
            return None
        return self.oms.submit(order, portfolio_state, reference_price=ref_price)

    # ------------------------------------------------------------------ run

    def run_once(self) -> DaemonRunReport:
        run_ts = datetime.now(UTC)
        log.info(
            "daemon.run.start",
            profile=self.profile.name.value,
            universe=len(self.universe),
            mode=settings.trading_mode,
        )

        if self.kill_switch.is_engaged():
            log.warning("daemon.kill_switch_engaged", reason=self.kill_switch.reason)
            return DaemonRunReport(
                ts=run_ts, profile_name=self.profile.name.value,
                nav=0.0, cash=0.0, n_positions_before=0,
                n_signals_evaluated=0, n_selected=0,
                n_orders_attempted=0, n_orders_accepted=0, n_orders_rejected=0,
                aggregator_result=None, error="kill_switch_engaged",
            )

        try:
            equity, cash, positions = self._account_snapshot()
        except Exception as exc:
            log.error("daemon.account_snapshot_failed", error=str(exc))
            return DaemonRunReport(
                ts=run_ts, profile_name=self.profile.name.value,
                nav=0.0, cash=0.0, n_positions_before=0,
                n_signals_evaluated=0, n_selected=0,
                n_orders_attempted=0, n_orders_accepted=0, n_orders_rejected=0,
                aggregator_result=None, error=f"account_snapshot_failed: {exc}",
            )

        self.circuit_breaker.update(equity, run_ts)
        if self.circuit_breaker.state.value != "ok":
            log.warning("daemon.circuit_breaker_tripped", state=self.circuit_breaker.state.value)
            return DaemonRunReport(
                ts=run_ts, profile_name=self.profile.name.value,
                nav=equity, cash=cash, n_positions_before=len(positions),
                n_signals_evaluated=0, n_selected=0,
                n_orders_attempted=0, n_orders_accepted=0, n_orders_rejected=0,
                aggregator_result=None, error=f"breaker:{self.circuit_breaker.state.value}",
            )

        histories = self._pull_history(run_ts)
        log.info(
            "daemon.history_pulled",
            universe_size=len(self.universe),
            symbols_with_data=len(histories),
            symbols_without_data=len(self.universe) - len(histories),
        )
        if not histories:
            log.warning(
                "daemon.no_data",
                hint=(
                    "All symbols returned empty. yfinance rate-limit from CI runner is "
                    "common — try fewer symbols or run from a different IP."
                ),
            )

        signals_by_symbol = self._evaluate_signals(histories)
        last_prices = {sym: float(df["close"].iloc[-1]) for sym, df in histories.items()}

        # Make sure positions held in symbols we no longer have data for still get
        # a last-known price from the broker if we can get it; otherwise warn.
        for sym in positions:
            if sym not in last_prices:
                log.warning("daemon.position_without_data", symbol=sym)

        result = self.aggregator.aggregate(
            signals_by_symbol=signals_by_symbol,
            price_history=histories,
            current_positions=positions,
            last_prices=last_prices,
            nav=equity,
        )

        # Build PortfolioState for risk checks.
        positions_notional = {sym: qty * last_prices.get(sym, 0.0) for sym, qty in positions.items()}
        portfolio_state = PortfolioState(
            nav=equity,
            cash=cash,
            positions_notional=positions_notional,
            sector_notional={},  # not tracked yet
        )

        n_attempted = 0
        n_accepted = 0
        n_rejected = 0
        for target in result.orders:
            n_attempted += 1
            log.info(
                "daemon.intended_order",
                symbol=target.symbol,
                side=target.side,
                qty=target.qty,
            )
            submitted = self._submit_order(target, portfolio_state, last_prices)
            if submitted is None:
                n_rejected += 1
                continue
            if submitted.status.value == "rejected":
                n_rejected += 1
            else:
                n_accepted += 1

        report = DaemonRunReport(
            ts=run_ts,
            profile_name=self.profile.name.value,
            nav=equity,
            cash=cash,
            n_positions_before=len(positions),
            n_signals_evaluated=sum(len(s) for s in signals_by_symbol.values()),
            n_selected=len(result.selected),
            n_orders_attempted=n_attempted,
            n_orders_accepted=n_accepted,
            n_orders_rejected=n_rejected,
            aggregator_result=result,
        )
        log.info(
            "daemon.run.complete",
            profile=self.profile.name.value,
            nav=equity,
            n_selected=len(result.selected),
            n_orders_attempted=n_attempted,
            n_orders_accepted=n_accepted,
            n_orders_rejected=n_rejected,
        )
        return report
