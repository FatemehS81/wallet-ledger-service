# Wallet & Ledger Service

A small, production-minded wallet service built with Django, Django REST
Framework and PostgreSQL. Each user owns one wallet and can credit or debit it.
Every balance change is an immutable ledger entry; the current balance is a
denormalised value updated in the same transaction and can always be verified
from the ledger.

The full analysis and design is in [`docs/analysis.md`](docs/analysis.md), and
the decisions log (including any deviation) is in
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## What it does

- Records a balance increase (`POST /api/v1/wallet/credit`)
- Records a balance decrease (`POST /api/v1/wallet/debit`)
- Shows the current balance (`GET /api/v1/wallet/balance`)
- Shows the complete history (`GET /api/v1/wallet/transactions`)
- Registers users and creates their wallet atomically
- Authenticates with JWT access and refresh tokens, with rotation and blacklist
- Guarantees the balance never becomes negative
- Makes retries safe with a client-generated `Idempotency-Key`
- Verifies the ledger with `manage.py verify_ledger`

## Design highlights

- **Append-only ledger is the source of truth.** `LedgerEntry` rows are never
  updated or deleted; the model, its custom queryset, and `on_delete=PROTECT`
  enforce this at the application level.
- **Per-wallet row lock.** Every credit/debit runs in `transaction.atomic()`
  and takes `SELECT ... FOR UPDATE` on the wallet row. Requests for one wallet
  are serialised; different wallets never block each other.
- **Idempotency.** The `Idempotency-Key` header is required and must be a UUID.
  A replay with the same key and the same type/amount returns the original
  response with `200`; the same key with a different type/amount returns `409`.
- **Defence in depth.** Database `CHECK` constraints, a unique
  `(wallet, idempotency_key)` constraint and a non-negative balance constraint
  back up the application rules.
- **Uniform errors.** Every error has the shape
  `{"error": {"code": "...", "message": "...", "details": {...}}}`.
- **Verification.** `verify_wallet()` recomputes the balance and checks the
  `balance_after` chain; `manage.py verify_ledger` reports any inconsistency and
  exits non-zero.

## Requirements

- Docker and Docker Compose (the recommended way to run everything)
- Python 3.12 for running the suite or tools directly from a virtualenv
- PostgreSQL 16 (provided by the compose files)

## Quick start (development)

```bash
cp .env.dev.example .env.dev
make dev-up
docker compose -p wallet-dev -f docker-compose.yml -f docker-compose.dev.yml \
  exec web python manage.py migrate
```

The API is then available at `http://localhost:8000/api/v1/`. Swagger UI is at
`http://localhost:8000/api/docs/` (and the raw schema at `/api/schema/`).

Stop it with `make dev-down`.

## Running tests

The test environment uses its own PostgreSQL service on `tmpfs`, its own
credentials and its own compose project, so it can never touch dev or prod data.

```bash
make test
```

`make test` builds the test image, runs `pytest` with the coverage gate and
tears the environment down afterwards.

For a faster local loop, start the test database and run pytest from a
virtualenv:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements/dev.txt
docker compose -p wallet-test -f docker-compose.yml -f docker-compose.test.yml up -d db
DB_HOST=127.0.0.1 DB_PORT=5433 .venv/bin/python -m pytest
```

The concurrency tests need real PostgreSQL and `transaction=True`; they must not
be run against SQLite.

## Quality gates

```bash
make lint    # ruff check . and ruff format --check .
make format  # ruff check --fix . and ruff format .
make docs    # spectacular --validate --fail-on-warn
```

The suite enforces a 90% coverage floor (tests and migrations are omitted from
the coverage measurement).

## Environments

Three fully separated environments are provided. Each has its own settings
module, database service, volume, credentials and compose project name.

| Environment | Settings | Compose files | Project name | Database |
| --- | --- | --- | --- | --- |
| dev | `config.settings.dev` | `docker-compose.yml` + `docker-compose.dev.yml` | `wallet-dev` | `wallet`, persistent volume, port 5434 |
| test | `config.settings.test` | `docker-compose.yml` + `docker-compose.test.yml` | `wallet-test` | `wallet_test`, `tmpfs`, port 5433 |
| prod | `config.settings.prod` | `docker-compose.yml` + `docker-compose.prod.yml` | `wallet-prod` | `wallet`, persistent volume, no published port |

Commands:

```bash
make dev-up      make dev-down
make test
make prod-up     make prod-down
make migrate     # explicit production migration step
make verify      # verify_ledger against the development database
```

Production refuses to start if `SECRET_KEY`, `ALLOWED_HOSTS` or the database
credentials are missing. Copy `.env.prod.example` to `.env.prod` and fill in real
values first. Only `.env.*.example` files are committed; real `.env` files are
git-ignored. Production does not run migrations automatically: `make migrate` is
an explicit step so several instances cannot race each other.

## API

All endpoints live under `/api/v1/`. Wallet endpoints always act on the
authenticated user's own wallet; no user id appears in any URL.

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/auth/register` | No | Create user and wallet in one transaction |
| POST | `/auth/login` | No | Obtain access and refresh tokens |
| POST | `/auth/refresh` | No | Rotate tokens |
| POST | `/auth/logout` | Yes | Blacklist the refresh token |
| POST | `/wallet/credit` | Yes | Increase balance. Requires `Idempotency-Key` |
| POST | `/wallet/debit` | Yes | Decrease balance. Requires `Idempotency-Key` |
| GET | `/wallet/balance` | Yes | Current balance |
| GET | `/wallet/transactions` | Yes | Cursor-paginated history |

Example:

```bash
curl -X POST http://localhost:8000/api/v1/wallet/credit \
  -H "Authorization: Bearer <access token>" \
  -H "Idempotency-Key: 3b241101-e2bb-4255-8caf-4136c566a962" \
  -H "Content-Type: application/json" \
  -d '{"amount": 500, "description": "Top-up"}'
```

Amounts are integers in minor units. Strings, floats, booleans, `null`, zero and
negative values are rejected. The first successful request returns `201`; an
idempotent replay returns `200` with the original body.

## Error catalogue

| HTTP | `code` | When |
| --- | --- | --- |
| 400 | `validation_error` | Invalid body or query parameter |
| 400 | `amount_limit_exceeded` | Amount above `MAX_TRANSACTION_AMOUNT` |
| 400 | `invalid_idempotency_key` | Header missing or not a valid UUID |
| 400 | `username_taken` | Registration with an existing username |
| 401 | `not_authenticated` | Token missing, invalid or expired |
| 404 | `wallet_not_found` | The user has no wallet |
| 409 | `idempotency_conflict` | Same key with a different type or amount |
| 422 | `insufficient_funds` | Debit larger than the balance |
| 422 | `balance_limit_exceeded` | Credit would exceed `MAX_WALLET_BALANCE` |
| 500 | `internal_error` | Unexpected failure; details are logged, never returned |

## Branching model (Gitflow)

- `main`: released, tagged states only
- `develop`: integration branch for finished features
- `feature/<name>`: one per implementation phase, merged into `develop` with a
  merge commit (`--no-ff`)
- `release/1.0.0`: version bump and changelog, merged into `main` and `develop`
- `hotfix/<name>`: only for post-release defects

Commits follow Conventional Commits. Feature branches are kept after merging so
the history stays reviewable. See `git log --graph --oneline --all`.

## CI/CD

- `.github/workflows/ci.yml` runs on pushes to `main`, `develop`, `feature/**`,
  `release/**`, `hotfix/**` and on pull requests into `main`/`develop`. Jobs:
  lint, test (PostgreSQL 16 service, migration check, schema validation, pytest
  with coverage) and a production Docker build. It is also callable by CD.
- `.github/workflows/cd.yml` runs on `v*` tags. It reuses CI, builds and pushes
  the image to GitHub Container Registry (`ghcr.io/<owner>/<repo>`) with the
  built-in `GITHUB_TOKEN`, then runs a documented deploy placeholder bound to
  the `production` environment. No deployment target was specified, so the
  placeholder only prints the intended migration and rollout steps.

### Manual GitHub settings

These cannot be committed as code and must be configured by the repository
owner:

1. Enable branch protection on `main` and `develop` and require the CI checks
   (`Lint`, `Test`, `Docker build`) before merging.
2. Configure the `production` environment with a required reviewer.
3. Ensure Actions has permission to publish packages to GHCR (the workflow
   requests `packages: write`).

## Known limitations

- Access tokens stay valid until they expire even after logout; the blacklist
  applies to refresh tokens.
- Users created outside registration (for example `createsuperuser`) have no
  wallet and receive `wallet_not_found`.
- Any authenticated user can credit their own wallet (assumption A4). A real
  system would put credit behind a payment gateway or an admin role.
- Idempotency keys never expire.
- No database `lock_timeout`, so a stalled transaction can make others wait.
- Writes to a single wallet are serialised by design, which bounds per-wallet
  throughput.
- Raw SQL can bypass the append-only guards; verification detects it but does
  not prevent it.
- No rate limiting, e-mail verification, password reset or transfers.
- CD does not deploy anywhere; the deploy job is a placeholder.
- Swagger UI is off in production unless `SWAGGER_ENABLED=true`.

## Future improvements

- Transfers between wallets with ordered lock acquisition to avoid deadlocks
- A reversal/refund flow built on compensating entries
- A PostgreSQL trigger to enforce append-only at the database level
- `lock_timeout` and `statement_timeout`
- A staging environment
- Structured logs, request ids, metrics and a scheduled `verify_ledger` job
- An idempotency-key retention policy
- Ledger partitioning if volume requires it
- A real deployment job once a target exists
