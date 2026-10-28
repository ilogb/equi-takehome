.PHONY: dev api worker web test eval migrate keys

dev:
	docker compose up --build

api:
	cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

worker:
	cd backend && uv run python -m app.worker

web:
	npm --prefix web run dev

test:
	cd backend && uv run pytest tests/unit -v

eval:
	cd backend && uv run python -m evals.run

migrate:
	cd backend && uv run alembic upgrade head

keys:
	@echo "SESSION_SECRET=$$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
	@echo "FERNET_KEY=$$(cd backend && uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
