PYTHON ?= .venv/bin/python
COMPOSE ?= docker compose
DEV := $(COMPOSE) -p wallet-dev -f docker-compose.yml -f docker-compose.dev.yml
TEST := $(COMPOSE) -p wallet-test -f docker-compose.yml -f docker-compose.test.yml
PROD := $(COMPOSE) -p wallet-prod -f docker-compose.yml -f docker-compose.prod.yml

.PHONY: help dev-up dev-down test test-local prod-up prod-down migrate verify lint format docs

help:
	@echo "dev-up     build and start the development environment"
	@echo "dev-down   stop the development environment"
	@echo "test       run the full suite against the isolated test database"
	@echo "test-local run the suite from the local virtualenv (test DB on port 5433)"
	@echo "prod-up    build and start the production environment (requires .env.prod)"
	@echo "prod-down  stop the production environment"
	@echo "migrate    run migrations explicitly in the production container"
	@echo "verify     run verify_ledger against the development database"
	@echo "lint       ruff check and ruff format --check"
	@echo "format     ruff check --fix and ruff format"
	@echo "docs       validate the OpenAPI schema (zero warnings allowed)"

dev-up:
	$(DEV) up --build -d

dev-down:
	$(DEV) down

test:
	$(TEST) up --build --abort-on-container-exit --exit-code-from web web; \
	status=$$?; $(TEST) down -v; exit $$status

test-local:
	DB_HOST=127.0.0.1 DB_PORT=5433 $(PYTHON) -m pytest

prod-up:
	@test -f .env.prod || (echo "Missing .env.prod; copy .env.prod.example first." && exit 1)
	$(PROD) up --build -d

prod-down:
	$(PROD) down

migrate:
	$(PROD) exec web python manage.py migrate

verify:
	$(DEV) exec web python manage.py verify_ledger

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

docs:
	$(PYTHON) manage.py spectacular --validate --fail-on-warn --file /dev/null
