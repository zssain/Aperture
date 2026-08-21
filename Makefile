.PHONY: help install dev test lint typecheck migrate seed seed-demo up down verify-deployment

help:
	@echo "Aperture — available targets:"
	@echo "  install    Install backend (uv) and frontend (npm) dependencies"
	@echo "  up/down    Start/stop the Postgres container via docker compose"
	@echo "  dev        Run the API (:8000) and the SPA (:5173) together"
	@echo "  test       Run backend (pytest) and frontend (vitest) tests"
	@echo "  lint       Run ruff, mypy --strict, import contracts and eslint"
	@echo "  typecheck  Run mypy --strict and tsc --noEmit"
	@echo "  migrate    Apply database migrations (configured from stage 01)"
	@echo "  seed       Load seed data (configured in a later stage)"

install:
	cd backend && uv sync
	cd frontend && npm install

up:
	docker compose up -d

down:
	docker compose down

dev:
	@echo "Starting API on :8000 and SPA on :5173 (Ctrl-C to stop both)…"
	@trap 'kill 0' EXIT; \
		( cd backend && uv run uvicorn app.main:app --reload --port 8000 ) & \
		( cd frontend && npm run dev ) & \
		wait

test:
	cd backend && uv run pytest
	cd frontend && npm run test

lint:
	cd backend && uv run ruff check . && uv run mypy --strict app tests && uv run lint-imports
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy --strict app tests
	cd frontend && npm run typecheck

migrate:
	cd backend && uv run alembic upgrade head

seed:
	@echo "No seed data yet — seeding is configured in a later stage."

seed-demo:
	cd backend && uv run python scripts/seed_demo.py

verify-deployment:
	cd backend && uv run python scripts/verify_deployment.py
