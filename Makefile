.PHONY: help install dev test lint typecheck migrate seed seed-demo demo-reset demo-statements demo-flip up down verify-deployment

help:
	@echo "Aperture — available targets:"
	@echo "  install    Install backend (uv) and frontend (npm) dependencies"
	@echo "  up/down    Start/stop the Postgres container via docker compose"
	@echo "  dev        Run the API (:8000), job worker and the SPA (:5173) together"
	@echo "  test       Run backend (pytest) and frontend (vitest) tests"
	@echo "  lint       Run ruff, mypy --strict, import contracts and eslint"
	@echo "  typecheck  Run mypy --strict and tsc --noEmit"
	@echo "  migrate    Apply database migrations (configured from stage 01)"
	@echo "  seed       Load seed data (configured in a later stage)"
	@echo "  demo-reset      Wipe and reseed the demo book, regenerate demo statements"
	@echo "  demo-statements Regenerate demo/statements files with today's dates"
	@echo "  demo-flip       Fire verified-income events at the declined demo applicant"
	@echo "  demo-ids        Print the demo case URLs (Meera fraud, Kabir flip)"

install:
	cd backend && uv sync
	cd frontend && npm install

up:
	docker compose up -d

down:
	docker compose down

dev:
	@echo "Starting API on :8000, job worker, and SPA on :5173 (Ctrl-C to stop all)…"
	@trap 'kill 0' EXIT; \
		( cd backend && uv run uvicorn app.main:app --reload --port 8000 ) & \
		( cd backend && uv run python -m app.worker ) & \
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

demo-reset:
	cd backend && DEMO_SEED_ENABLED=true uv run python scripts/demo_reset.py
	cd backend && uv run python scripts/generate_demo_statements.py

demo-statements:
	cd backend && uv run python scripts/generate_demo_statements.py

demo-flip:
	cd backend && uv run python scripts/demo_flip.py

demo-ids:
	cd backend && uv run python scripts/demo_ids.py

verify-deployment:
	cd backend && uv run python scripts/verify_deployment.py
