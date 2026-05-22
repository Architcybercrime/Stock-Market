"""Model registry: filesystem-backed by default, MLflow-compatible.

Every registered model has:
- A unique (model_id, version) key
- Its weights/artifacts under a versioned directory
- Frozen metadata at registration time
- Validation metrics from walk-forward
- A pointer to the feature bundle it expects

For Phase 1 we use the local filesystem. Swapping in MLflow only requires
changing register/load to call mlflow client methods.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from libs.common.logging import get_logger
from services.ml.models.base import Model

log = get_logger(__name__)


class ModelRegistry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _model_dir(self, model_id: str, version: str) -> Path:
        return self.root / model_id / version

    def register(
        self,
        model: Model,
        validation_metrics: dict[str, float] | None = None,
        notes: str = "",
    ) -> Path:
        """Persist a model under (model_id, version). Errors if version exists."""
        meta = model.metadata
        target = self._model_dir(meta.model_id, meta.version)
        if target.exists():
            raise FileExistsError(f"model already registered: {meta.model_id}@{meta.version}")
        target.mkdir(parents=True, exist_ok=False)

        model.save(target / "artifact")

        manifest = {
            "model_id": meta.model_id,
            "version": meta.version,
            "family": meta.family,
            "feature_bundle": meta.feature_bundle,
            "trained_at": meta.trained_at.isoformat(),
            "registered_at": datetime.now(UTC).isoformat(),
            "train_window": [t.isoformat() for t in meta.train_window],
            "label_horizon_bars": meta.label_horizon_bars,
            "label_definition": meta.label_definition,
            "metrics": meta.metrics,
            "validation_metrics": validation_metrics or {},
            "notes": notes or meta.notes,
        }
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

        # Update the "latest" pointer for this model_id.
        latest_file = self.root / meta.model_id / "LATEST"
        latest_file.parent.mkdir(parents=True, exist_ok=True)
        latest_file.write_text(meta.version)

        log.info("registry.register", model_id=meta.model_id, version=meta.version, family=meta.family)
        return target

    def list(self) -> list[dict]:
        """List all registered models."""
        out: list[dict] = []
        if not self.root.exists():
            return out
        for model_dir in self.root.iterdir():
            if not model_dir.is_dir():
                continue
            for version_dir in model_dir.iterdir():
                if not version_dir.is_dir():
                    continue
                manifest_path = version_dir / "manifest.json"
                if manifest_path.exists():
                    out.append(json.loads(manifest_path.read_text()))
        return out

    def latest_version(self, model_id: str) -> str | None:
        latest = self.root / model_id / "LATEST"
        if not latest.exists():
            return None
        return latest.read_text().strip()

    def load(self, model_id: str, version: str | None = None) -> Model:
        from services.ml.models.ensemble import WeightedEnsemble
        from services.ml.models.lstm_model import LSTMModel
        from services.ml.models.xgboost_model import XGBoostModel

        if version is None:
            version = self.latest_version(model_id)
            if version is None:
                raise FileNotFoundError(f"no versions for {model_id}")
        target = self._model_dir(model_id, version)
        manifest = json.loads((target / "manifest.json").read_text())
        family = manifest["family"]
        loaders: dict[str, type[Model]] = {
            "xgboost": XGBoostModel,
            "lstm": LSTMModel,
            "ensemble": WeightedEnsemble,
        }
        if family not in loaders:
            raise ValueError(f"unknown model family: {family}")
        return loaders[family].load(target / "artifact")

    def delete(self, model_id: str, version: str) -> None:
        """Delete a registered version. Irreversible."""
        target = self._model_dir(model_id, version)
        if target.exists():
            shutil.rmtree(target)
            log.warning("registry.delete", model_id=model_id, version=version)
        latest = self.root / model_id / "LATEST"
        if latest.exists() and latest.read_text().strip() == version:
            latest.unlink()
