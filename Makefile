.PHONY: up down test lint build logs shell

# Start all services (db, redis, ollama, api, frontend, nginx)
up:
	docker compose up -d

# Stop all services
down:
	docker compose down

# Build/rebuild all images
build:
	docker compose build

# Run full lint + test suite inside Docker
test:
	docker compose run --rm test

# Lint only (no tests)
lint:
	docker compose run --rm --no-deps test sh -c "ruff check app/ tests/ && ruff format --check app/ tests/"

# Tail API logs
logs:
	docker compose logs -f api

# Shell into the running API container
shell:
	docker compose exec api bash
