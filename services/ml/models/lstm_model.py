"""LSTM model in PyTorch Lightning.

Predicts next-bar log return from a window of feature vectors. MC-dropout at
inference gives a simple uncertainty estimate. Training is deterministic given
a seed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.ml.models.base import Model, ModelMetadata, Prediction


class _LSTMNet:
    """Lazy-import wrapper so importing this module doesn't pull torch."""

    @staticmethod
    def build(input_dim: int, hidden_dim: int, num_layers: int, dropout: float):
        import torch
        import torch.nn as nn

        class Net(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size=input_dim,
                    hidden_size=hidden_dim,
                    num_layers=num_layers,
                    dropout=dropout if num_layers > 1 else 0.0,
                    batch_first=True,
                )
                self.dropout = nn.Dropout(dropout)
                self.head = nn.Linear(hidden_dim, 1)

            def forward(self, x: "torch.Tensor") -> "torch.Tensor":
                out, _ = self.lstm(x)
                last = out[:, -1, :]
                return self.head(self.dropout(last)).squeeze(-1)

        return Net()


class LSTMModel(Model):
    """Sequence model on a rolling window of features.

    Input shape: (n_samples, seq_len, n_features).
    """

    family: str = "lstm"

    def __init__(
        self,
        feature_columns: list[str],
        seq_len: int = 30,
        hidden_dim: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        lr: float = 1e-3,
        max_epochs: int = 30,
        batch_size: int = 64,
        device: str = "auto",
        seed: int = 42,
        metadata: ModelMetadata | None = None,
    ) -> None:
        self.feature_columns = list(feature_columns)
        self.seq_len = seq_len
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.dropout = dropout
        self.lr = lr
        self.max_epochs = max_epochs
        self.batch_size = batch_size
        self.device = device
        self.seed = seed
        self._net: Any = None
        self._feature_mean: np.ndarray | None = None
        self._feature_std: np.ndarray | None = None
        self.metadata = metadata or ModelMetadata(
            model_id="lstm",
            version="dev",
            family=self.family,
            feature_bundle="baseline_v1@1.0.0",
            trained_at=datetime.now(UTC),
            train_window=(datetime.now(UTC), datetime.now(UTC)),
            label_horizon_bars=1,
            label_definition="log_return_next_1",
        )

    # ------------------------------------------------------------------ training

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "LSTMModel":
        import torch
        from torch.utils.data import DataLoader, TensorDataset

        torch.manual_seed(self.seed)
        np.random.seed(self.seed)

        seqs, targets = self._make_sequences(X, y)
        if len(seqs) == 0:
            raise ValueError(f"not enough rows for seq_len={self.seq_len}")

        # Standardize features using train statistics only.
        flat = seqs.reshape(-1, seqs.shape[-1])
        self._feature_mean = flat.mean(axis=0)
        self._feature_std = flat.std(axis=0) + 1e-8
        seqs = (seqs - self._feature_mean) / self._feature_std

        device = self._resolve_device()
        self._net = _LSTMNet.build(
            input_dim=len(self.feature_columns),
            hidden_dim=self.hidden_dim,
            num_layers=self.num_layers,
            dropout=self.dropout,
        ).to(device)

        opt = torch.optim.Adam(self._net.parameters(), lr=self.lr)
        loss_fn = torch.nn.MSELoss()

        x_t = torch.tensor(seqs, dtype=torch.float32)
        y_t = torch.tensor(targets, dtype=torch.float32)
        loader = DataLoader(TensorDataset(x_t, y_t), batch_size=self.batch_size, shuffle=True)

        self._net.train()
        for _epoch in range(self.max_epochs):
            for xb, yb in loader:
                xb = xb.to(device)
                yb = yb.to(device)
                opt.zero_grad()
                pred = self._net(xb)
                loss = loss_fn(pred, yb)
                loss.backward()
                opt.step()
        return self

    # ------------------------------------------------------------------ inference

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        import torch

        if self._net is None:
            raise RuntimeError("model not fit")
        self._net.eval()
        seqs, _ = self._make_sequences(X, y=None)
        if len(seqs) == 0:
            return np.array([])
        seqs = (seqs - self._feature_mean) / self._feature_std
        device = self._resolve_device()
        with torch.no_grad():
            out = self._net(torch.tensor(seqs, dtype=torch.float32).to(device))
        return out.cpu().numpy()

    def predict_one(self, X: pd.DataFrame) -> Prediction:
        """Single prediction with MC-dropout uncertainty."""
        import torch

        if self._net is None:
            raise RuntimeError("model not fit")
        if len(X) < self.seq_len:
            raise ValueError(f"need at least {self.seq_len} rows for one prediction")

        seqs, _ = self._make_sequences(X.tail(self.seq_len + 1), y=None)
        if len(seqs) == 0:
            raise ValueError("not enough rows after windowing")
        seqs = (seqs - self._feature_mean) / self._feature_std
        device = self._resolve_device()
        x_t = torch.tensor(seqs[-1:], dtype=torch.float32).to(device)

        # MC dropout: leave net in train() mode for dropout layers, no grad.
        self._net.train()
        with torch.no_grad():
            samples = np.stack([self._net(x_t).cpu().numpy() for _ in range(30)])
        self._net.eval()
        mean = float(samples.mean())
        std = float(samples.std())
        return Prediction(point=mean, lower=mean - 2 * std, upper=mean + 2 * std)

    # ------------------------------------------------------------------ persistence

    def save(self, path: Path) -> None:
        import torch

        if self._net is None:
            raise RuntimeError("nothing to save")
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        torch.save(self._net.state_dict(), path / "weights.pt")
        np.savez(
            path / "normalization.npz",
            mean=self._feature_mean,
            std=self._feature_std,
        )
        meta = {
            "feature_columns": self.feature_columns,
            "hyperparams": {
                "seq_len": self.seq_len,
                "hidden_dim": self.hidden_dim,
                "num_layers": self.num_layers,
                "dropout": self.dropout,
                "lr": self.lr,
                "max_epochs": self.max_epochs,
                "batch_size": self.batch_size,
                "seed": self.seed,
            },
            "metadata": {
                **self.metadata.__dict__,
                "trained_at": self.metadata.trained_at.isoformat(),
                "train_window": [t.isoformat() for t in self.metadata.train_window],
            },
        }
        (path / "meta.json").write_text(json.dumps(meta, indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> "LSTMModel":
        import torch

        path = Path(path)
        meta = json.loads((path / "meta.json").read_text())
        hp = meta["hyperparams"]
        m = meta["metadata"]

        metadata = ModelMetadata(
            model_id=m["model_id"],
            version=m["version"],
            family=m["family"],
            feature_bundle=m["feature_bundle"],
            trained_at=datetime.fromisoformat(m["trained_at"]),
            train_window=(
                datetime.fromisoformat(m["train_window"][0]),
                datetime.fromisoformat(m["train_window"][1]),
            ),
            label_horizon_bars=m["label_horizon_bars"],
            label_definition=m["label_definition"],
            metrics=m.get("metrics", {}),
            notes=m.get("notes", ""),
        )
        obj = cls(feature_columns=meta["feature_columns"], metadata=metadata, **hp)
        obj._net = _LSTMNet.build(
            input_dim=len(obj.feature_columns),
            hidden_dim=obj.hidden_dim,
            num_layers=obj.num_layers,
            dropout=obj.dropout,
        )
        obj._net.load_state_dict(torch.load(path / "weights.pt", map_location="cpu"))
        obj._net.eval()
        norm = np.load(path / "normalization.npz")
        obj._feature_mean = norm["mean"]
        obj._feature_std = norm["std"]
        return obj

    # ------------------------------------------------------------------ helpers

    def _make_sequences(
        self, X: pd.DataFrame, y: pd.Series | None
    ) -> tuple[np.ndarray, np.ndarray]:
        cols = self.feature_columns
        missing = set(cols) - set(X.columns)
        if missing:
            raise ValueError(f"missing feature columns: {sorted(missing)}")
        arr = X[cols].to_numpy(dtype=np.float32)
        n = len(arr)
        if n < self.seq_len:
            return np.empty((0, self.seq_len, len(cols)), dtype=np.float32), np.empty((0,), dtype=np.float32)
        seqs = np.lib.stride_tricks.sliding_window_view(arr, (self.seq_len, len(cols)))[:, 0, :, :]
        if y is not None:
            targets = y.to_numpy(dtype=np.float32)[self.seq_len - 1 :]
            assert len(targets) == len(seqs)
            return seqs, targets
        return seqs, np.empty((0,), dtype=np.float32)

    def _resolve_device(self) -> str:
        import torch

        if self.device != "auto":
            return self.device
        return "cuda" if torch.cuda.is_available() else "cpu"
