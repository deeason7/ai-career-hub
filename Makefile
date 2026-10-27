.PHONY: up down test test-frontend test-probes docs-check lint build logs shell evals

PYTEST_PIN := $(shell sed -n '/^pytest==/p' backend/requirements.dev.txt)
RUFF_PIN := $(shell sed -n '/^ruff==/p' backend/requirements.dev.txt)

# Start all services (db, redis, ollama, api, frontend, nginx)
up:
	docker compose up -d

# Stop all services
down:
	docker compose down

# Build/rebuild all images
build:
	docker compose build

# Run backend lint and tests against the isolated test database
test:
	docker compose run --rm test

# Framework tests run in the frontend image with the existing pytest pin.
test-frontend:
	docker compose run --rm --no-deps frontend sh -c "pip install -q '$(PYTEST_PIN)' && python -m pytest tests/ -v --tb=short"

test-probes:
	python3 -m unittest discover -s .github/scripts/tests -v

docs-check:
	python3 .github/scripts/check_docs.py

# Lint only (no tests) — backend via the test image, frontend via its own image
lint:
	docker compose run --rm --no-deps test sh -c "ruff check app/ tests/ evals/ && ruff format --check app/ tests/ evals/"
	docker compose run --rm --no-deps frontend sh -c "pip install -q '$(RUFF_PIN)' && ruff check . && ruff format --check ."

# Tail API logs
logs:
	docker compose logs -f api

# Shell into the running API container
shell:
	docker compose exec api bash

# Run an eval suite against the labeled corpus. Loads the sentence-transformers
# model, so the first run downloads ~80MB.
evals:
	docker compose run --rm --no-deps test python -m evals.runner
