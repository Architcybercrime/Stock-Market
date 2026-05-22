"""Centralized settings loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RiskLimits(BaseSettings):
    """Default risk limits. Overridable per portfolio at runtime."""

    model_config = SettingsConfigDict(env_prefix="RISK_", env_file=".env", extra="ignore")

    max_daily_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.10
    max_position_pct: float = 0.05
    max_sector_pct: float = 0.25
    max_leverage: float = 1.0
    min_cash_buffer_pct: float = 0.05
    max_orders_per_minute: int = 60
    max_order_notional_pct: float = 0.02


class Settings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Environment
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # Postgres
    postgres_user: str = "trader"
    postgres_password: SecretStr = SecretStr("trader")
    postgres_db: str = "stockmarket"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Object storage
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_bucket: str = "stockmarket-data"
    aws_access_key_id: SecretStr | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_region: str = "us-east-1"

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5000"

    # Data
    data_root: Path = Path("./data")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    jwt_secret: SecretStr = SecretStr("change-me")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Trading
    trading_mode: Literal["paper", "live"] = "paper"
    live_trading_enabled: bool = False

    # Risk limits
    risk: RiskLimits = Field(default_factory=RiskLimits)

    # Broker creds (optional)
    alpaca_api_key: SecretStr | None = None
    alpaca_api_secret: SecretStr | None = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # News
    newsapi_key: SecretStr | None = None

    @property
    def postgres_dsn(self) -> str:
        pw = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{pw}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_live(self) -> bool:
        """True only when both flags align AND the kill file is absent.

        Used as a gate, not as a status field. Callers should check at the moment
        of action, not cache the result.
        """
        if self.trading_mode != "live" or not self.live_trading_enabled:
            return False
        kill_file = self.data_root / "KILL_SWITCH"
        return not kill_file.exists()


@lru_cache(maxsize=1)
def _cached_settings() -> Settings:
    return Settings()


# Default singleton; callers can construct their own Settings() for tests.
settings = _cached_settings()
