.PHONY: help install dev-up dev-down lint format test type backtest train ingest api frontend clean

help:
	@echo "Targets:"
	@echo "  install     Install Python deps with dev extras"
	@echo "  dev-up      Start local Postgres + Redis + MinIO"
	@echo "  dev-down    Stop local stack"
	@echo "  lint        Ruff lint"
	@echo "  format      Black + Ruff fix"
	@echo "  type        mypy"
	@echo "  test        pytest"
	@echo "  ingest      Pull historical data (SYMBOLS=... START=YYYY-MM-DD)"
	@echo "  train       Train a model (SYMBOL=AAPL MODEL=lstm)"
	@echo "  backtest    Run a backtest (STRATEGY=momentum SYMBOLS=...)"
	@echo "  api         Run FastAPI dev server"
	@echo "  frontend    Run Next.js dev server"

install:
	pip install -e ".[dev]"

dev-up:
	docker compose up -d postgres redis minio

dev-down:
	docker compose down

lint:
	ruff check libs services scripts tests

format:
	ruff check --fix libs services scripts tests
	black libs services scripts tests

type:
	mypy libs services

test:
	pytest

SYMBOLS ?= AAPL MSFT SPY
START ?= 2018-01-01
ingest:
	python scripts/ingest_history.py --symbols $(SYMBOLS) --start $(START)

SYMBOL ?= AAPL
MODEL ?= lstm
train:
	python scripts/train_model.py --symbol $(SYMBOL) --model $(MODEL)

STRATEGY ?= momentum
backtest:
	python scripts/run_backtest.py --strategy $(STRATEGY) --symbols $(SYMBOLS)

api:
	uvicorn services.api.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
