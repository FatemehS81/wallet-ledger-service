# Wallet & Ledger Service: Analysis and Design Document

**Author:** Fatemeh Sarmady | **Status:** Draft for review | **Date:** 2026-11-01

## 1. Overview and Scope

This document analyses and designs a small wallet service in which a user owns a wallet and can increase (credit) and decrease (debit) its balance. The emphasis is on correctness, testability and defensible engineering decisions rather than feature breadth.

**Required capabilities**

- Record a balance increase
- Record a balance decrease
- Show the user's current balance
- Show the complete history of balance changes

**Hard requirements from the brief**

- The balance must never become negative.
- Every balance change is stored as an independent record.
- The current balance must be verifiable from the stored records.
- An invalid request must not leave partial data behind.
- The behaviour for duplicate or retried requests must be explicitly defined.

**Core design idea.** An append-only ledger is the source of truth. The wallet row holds a denormalised balance that is updated in the same database transaction as the ledger entry, under a per-wallet row lock. Retries are made safe by a client-generated idempotency key plus a request fingerprint. A verification function recomputes the balance from the ledger to prove the two agree.

**Stack.** Django, Django REST Framework, PostgreSQL, JWT authentication, pytest, drf-spectacular (Swagger), ruff, GitHub Actions, Docker Compose.

**Engineering requirements added by the owner**

- API documented with Swagger, with examples (section 13)
- Gitflow branching, with feature branches merged at the end (section 14)
- Ruff for linting and formatting (section 15)
- CI/CD on GitHub Actions (section 16)
- Separate dev, test and prod environments, each with its own database (section 12)

## 2. Assumptions and Out of Scope

The brief does not specify several things (registration, login, how wallets are created, who may credit a wallet). Each gap is resolved below as an explicit assumption so that it can be challenged in review.

| ID | Assumption | Rationale |
| --- | --- | --- |
| A1 | Single currency. Amounts are integers in the smallest currency unit. | Avoids rounding errors; comparison and summation are exact. |
| A2 | Each user has exactly one wallet, created in the same transaction as the user at registration. | A missing wallet becomes an abnormal state (404) instead of a lazy-create case that is racy under concurrency. |
| A3 | `amount` is always a positive integer. Direction is given by the entry type (CREDIT or DEBIT). | A sign-carrying amount invites sign bugs. |
| A4 | An authenticated user can credit and debit only their own wallet. | Satisfies the brief without inventing admin or payment flows. In a production system, credit would sit behind a payment gateway or an admin role. |
| A5 | Clients generate the `Idempotency-Key` (UUID v4) once per logical operation and reuse it on retries. | Only the client knows that two requests are the same intent. A server-generated key would be lost on a timeout. |
| A6 | The ledger is append-only. Mistakes are corrected with compensating entries. | Preserves the audit trail. A reversal endpoint is not implemented. |
| A7 | One PostgreSQL primary database. | Row locks and constraints give the required guarantees. Multi-region is out of scope. |
| A8 | Authentication is minimal but complete: register, login, refresh and logout with JWT. | The brief was silent. A standard flow avoids custom security code. |
| A9 | Only successful requests are stored and replayed. | A failed request changed nothing, so replaying it adds no safety, and the ledger stays a record of real balance changes only. |

**Out of scope (conscious decisions):** email or phone verification, password reset, rate limiting, roles and permissions, transfers between wallets, multiple currencies, reversal or refund endpoints, revoking access tokens before expiry, TTL cleanup of idempotency keys, a staging environment, database lock timeouts.

**Process assumptions.** The owner added documentation, version control and automation requirements on top of the brief: Swagger docs with examples, gitflow, ruff, and CI/CD on GitHub Actions. No deployment target was specified, so continuous delivery publishes a container image to GitHub Container Registry and the final deploy step is a documented placeholder.

## 3. Requirements Traceability

| Requirement | Design decision | Verified by |
| --- | --- | --- |
| Record a balance increase | `POST /wallet/credit`, `services.credit` | test\_services, test\_api\_wallet |
| Record a balance decrease | `POST /wallet/debit`, `services.debit` | test\_services, test\_api\_wallet |
| Show current balance | `GET /wallet/balance`, `Wallet.balance` | test\_api\_wallet |
| Show full history | `GET /wallet/transactions` with cursor pagination | test\_api\_wallet |
| Balance never negative | Check under row lock, `PositiveBigIntegerField`, DB CHECK constraints | test\_services, test\_models, test\_concurrency |
| Each change is an independent record | `LedgerEntry`, one row per change, append-only | test\_models, test\_services |
| Balance verifiable from records | `verify_wallet()`, `verify_ledger` command, `balance_after` chain | test\_verification |
| Invalid request leaves no partial history | Shape validation before the transaction, one atomic transaction for state changes | test\_services, test\_api\_wallet |
| Duplicate or retry behaviour defined | Idempotency key and request fingerprint (section 7) | test\_idempotency, test\_concurrency |
| Testable, maintainable, scalable | Layered design, per-wallet locks, indexed history queries | whole test suite |
| API documented with Swagger and examples | drf-spectacular schema and Swagger UI, examples for every request, response and error (section 13) | test\_api\_docs, schema validation in CI |
| Gitflow with separate branches merged at the end | main, develop, feature branches per phase, release branch and tag (section 14) | Branch graph review, protected branches with required CI |
| Simple linting | ruff check and ruff format (section 15) | Lint job in CI |
| CI/CD on GitHub Actions | ci.yml on every push and pull request, cd.yml on version tags (section 16) | Workflow runs on GitHub |
| Separate environments, each with its own database | dev, test and prod settings and compose files (section 12) | make test against the isolated test database |

## 4. Technology Choices

| Concern | Choice | Rationale | Alternative considered |
| --- | --- | --- | --- |
| Framework | Django and DRF | `transaction.atomic`, `select_for_update`, migrations and constraints are built in | FastAPI: no advantage here, more manual assembly |
| Database | PostgreSQL | Real row-level locking and CHECK constraints; needed to prove concurrency safety | SQLite: no reliable row locks |
| Money type | `PositiveBigIntegerField` in minor units | Exact arithmetic, simple comparisons | `DecimalField`: needed only for fractional currencies |
| Auth | `djangorestframework-simplejwt` with token blacklist | Standard, no hand-written crypto | Session auth: less suitable for API clients |
| Tests | pytest and pytest-django | Fixtures and parametrisation fit the many invalid-input cases | unittest |
| Packaging | Docker Compose, one file per environment | One-command reproducible setup | Local installs |
| API documentation | drf-spectacular | Generates OpenAPI from the code, serves Swagger UI, supports examples | Hand-written OpenAPI file: drifts from the code |
| Lint and format | ruff | One fast tool for linting, import sorting and formatting | flake8 plus isort plus Black |
| CI/CD | GitHub Actions | Requested by the owner, integrated with pull requests and tags | Other CI systems |
| Image registry | GitHub Container Registry | Authenticates with the built-in GITHUB\_TOKEN, no extra secrets | Docker Hub: needs separate credentials |

## 5. Data Model

### 5.1 Entities

```
User 1 ---- 1 Wallet 1 ---- * LedgerEntry
```

### 5.2 Wallet

| Field | Type | Notes |
| --- | --- | --- |
| id | BigAutoField | Primary key |
| user | OneToOneField(User, on\_delete=PROTECT) | One wallet per user |
| balance | PositiveBigIntegerField, default 0 | Denormalised current balance |
| created\_at, updated\_at | DateTimeField |  |

Constraint: `CHECK (balance >= 0)` as the last line of defence in the database.

### 5.3 LedgerEntry

| Field | Type | Notes |
| --- | --- | --- |
| id | BigAutoField | Within one wallet, ids increase in commit order because inserts are serialised by the wallet lock |
| wallet | ForeignKey(Wallet, on\_delete=PROTECT) | History cannot vanish with its wallet |
| type | CharField, choices CREDIT or DEBIT | Direction of the change |
| amount | PositiveBigIntegerField | Always greater than 0 |
| balance\_after | PositiveBigIntegerField | Wallet balance immediately after this entry |
| idempotency\_key | UUIDField | Supplied by the client |
| request\_fingerprint | CharField(64) | SHA-256 of the normalised payload |
| description | CharField(255), blank | Optional note or reference |
| created\_at | DateTimeField | Display and audit |

### 5.4 Constraints and indexes

- `CHECK (amount > 0)`
- `CHECK (balance_after >= 0)`
- `CHECK (type IN ('CREDIT', 'DEBIT'))`
- `UNIQUE (wallet, idempotency_key)`, which also serves the idempotency lookup
- Index on `(wallet, id)`, which serves the history query ordered by `-id` and cursor pagination

### 5.5 Append-only enforcement

- `save()` on an existing entry raises an error; `delete()` raises an error.
- A custom `QuerySet` blocks `update()` and `delete()`.
- Raw SQL can still bypass the application layer. This is detected by verification (section 6) and can be hardened with a PostgreSQL trigger, which is listed as a future improvement.

### 5.6 Request fingerprint

The fingerprint is `SHA-256` of a canonical JSON string built from `type` and `amount` only: keys sorted, compact separators, amount rendered as an integer. This guarantees that identical requests always hash identically.

`description` is deliberately excluded. Consequence, documented as intended behaviour: a retry with the same key and a different `description` returns the original result, and the new description is ignored.

### 5.7 Configurable limits

| Setting | Example value | Purpose |
| --- | --- | --- |
| `MAX_TRANSACTION_AMOUNT` | 10^12 | Upper bound for a single operation |
| `MAX_WALLET_BALANCE` | 10^15 | Upper bound for a balance |

Both are far below the bigint maximum (about 9.2 x 10^18), so `balance + amount` can never overflow the column. A transaction cap alone is not enough, because many valid credits could eventually exceed the column range, so the balance cap is checked as well.

## 6. Business Rules and Invariants

### 6.1 Rules

| Rule | Behaviour | Error |
| --- | --- | --- |
| Amount type | Must be a JSON integer. Strings, floats, booleans and null are rejected. | 400 `validation_error` |
| Amount range | 1 up to `MAX_TRANSACTION_AMOUNT` | 400 `validation_error` or `amount_limit_exceeded` |
| Description | Optional, trimmed, at most 255 characters | 400 `validation_error` |
| Debit | Requires `balance >= amount`. Debit equal to the balance is allowed and leaves 0. | 422 `insufficient_funds` |
| Credit | Requires `balance + amount <= MAX_WALLET_BALANCE` | 422 `balance_limit_exceeded` |
| Ledger | Each successful change creates exactly one entry. Entries are never updated or deleted. | n/a |
| Corrections | Made with a compensating entry, never by editing history | n/a |

### 6.2 Invariants

- **I1:** `wallet.balance == sum(CREDIT amounts) - sum(DEBIT amounts)`
- **I2:** For every entry, `balance_after == previous.balance_after +/- amount`, where the first entry starts from 0
- **I3:** `0 <= wallet.balance <= MAX_WALLET_BALANCE` at all times
- **I4:** The latest entry's `balance_after == wallet.balance`

### 6.3 Verification

`verify_wallet(wallet)` recomputes the balance from the ledger and checks I1, I2 and I4. The management command `manage.py verify_ledger` runs it for all wallets, reports inconsistencies and exits with a non-zero code if any are found. There is intentionally no public verification endpoint; the check is an internal and operational tool and is used heavily in tests.

### 6.4 Atomicity

Shape validation (types, ranges, header format) happens before the transaction. Everything that depends on state (idempotency lookup, balance checks, entry creation, balance update) happens inside one `transaction.atomic()` under the wallet lock. Any failure rolls back, so no partial history can exist.

## 7. Idempotency Design

### 7.1 Client contract

- The client generates a UUID v4 when the user triggers a logical operation, for example pressing a withdraw button.
- Every retry of that operation sends the same key. A new operation gets a new key.
- The key is sent in the `Idempotency-Key` header. It is required on credit and debit.

### 7.2 Server flow

1. Authenticate the user and resolve their wallet.
2. Validate the header (present, valid UUID) and the body shape.
3. Compute the fingerprint from `type` and `amount`.
4. Start `transaction.atomic()` and lock the wallet row with `select_for_update()`.
5. Look up an entry by `(wallet, idempotency_key)` inside the lock.
   - Found and fingerprint equal: return the stored entry (replay).
   - Found and fingerprint different: raise `IdempotencyConflict`.
   - Not found: continue.
6. Check business rules (sufficient funds or balance cap).
7. Insert the `LedgerEntry` with `balance_after`, then update `wallet.balance`.
8. Commit and respond.

The lookup happens inside the lock on purpose. If it ran before the lock, two simultaneous retries could both see no entry and both write.

### 7.3 Behaviour table

| Situation | Response | New record |
| --- | --- | --- |
| First successful request | 201 | Yes |
| Retry, same key, same type and amount | 200 with the original body | No |
| Same key, different type or amount | 409 `idempotency_conflict` | No |
| Same key, different description only | 200 with the original body, new description ignored | No |
| Insufficient funds | 422 | No |
| Invalid input | 400 | No |

### 7.4 Edge cases

- **Retry after a failure.** Failures are not stored, so a retry with the same key is evaluated again. A debit rejected for insufficient funds can succeed on retry after a credit.
- **Key scope.** Keys are unique per wallet, not globally. Two users may use the same UUID without interference.
- **Replay body.** The response is built from the stored entry, so `balance_after` is the value at the time of the original operation, not the current balance.
- **Key lifetime.** Keys live as long as ledger entries. Cleanup is out of scope.
- **Unique violation as a safety net.** If the unique constraint ever fires despite the lock, the `IntegrityError` is caught and converted into the same found-entry logic after the failed transaction has rolled back.

## 8. Concurrency Design

### 8.1 Threats

| Threat | Example | Effect without protection |
| --- | --- | --- |
| Concurrent debits | Balance 1000, two debits of 800 at once | Both see enough funds; balance goes negative or an update is lost |
| Concurrent retries | Client times out and resends while the first request is still running | Same operation recorded twice |
| Partial writes | Crash between the entry insert and the balance update | Ledger and balance disagree |

### 8.2 Solution: pessimistic row lock per wallet

```python
def apply_entry(user, entry_type, amount, key, description):
    fingerprint = make_fingerprint(entry_type, amount)
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(user=user)
        existing = LedgerEntry.objects.filter(
            wallet=wallet, idempotency_key=key
        ).first()
        if existing:
            if existing.request_fingerprint != fingerprint:
                raise IdempotencyConflict()
            return existing, False
        new_balance = compute_new_balance(wallet.balance, entry_type, amount)
        entry = LedgerEntry.objects.create(
            wallet=wallet, type=entry_type, amount=amount,
            balance_after=new_balance, idempotency_key=key,
            request_fingerprint=fingerprint, description=description,
        )
        wallet.balance = new_balance
        wallet.save(update_fields=['balance', 'updated_at'])
    return entry, True
```

`compute_new_balance` raises `InsufficientFunds` or `BalanceLimitExceeded` before anything is written.

Requests for one wallet are serialised by the lock, which resolves all three threats with one mechanism. Different wallets never block each other, so the design scales with the number of wallets.

### 8.3 Isolation level

PostgreSQL default `READ COMMITTED` is used. Correctness depends on the row lock, not on a stronger isolation level. `SERIALIZABLE` is not used because it introduces serialisation failures that the application would have to retry.

### 8.4 Defence in depth

| Layer | Guarantees |
| --- | --- |
| `select_for_update` | Requests on one wallet run one at a time |
| `transaction.atomic` | All or nothing |
| `UNIQUE (wallet, idempotency_key)` | A duplicate record is impossible even if the lock were bypassed |
| CHECK constraints | A negative balance or non-positive amount cannot be stored |

### 8.5 Implementation notes

- Each operation locks exactly one wallet, so deadlocks cannot occur. If transfers are added later, locks must be acquired in ascending wallet id order.
- No external I/O (HTTP calls, e-mail) happens inside the transaction, to keep lock time short.
- A database `lock_timeout` is recommended as a future improvement so a request never waits indefinitely.

## 9. API Specification

All endpoints are under `/api/v1/` and use JSON. Wallet endpoints always act on the authenticated user's own wallet. No user id appears in any URL, which removes the possibility of reaching another user's wallet by changing an id (IDOR).

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/auth/register` | No | Create user and wallet in one transaction |
| POST | `/auth/login` | No | Obtain access and refresh tokens |
| POST | `/auth/refresh` | No | Rotate tokens |
| POST | `/auth/logout` | Yes | Blacklist the refresh token |
| POST | `/wallet/credit` | Yes | Increase balance. Requires `Idempotency-Key` |
| POST | `/wallet/debit` | Yes | Decrease balance. Requires `Idempotency-Key` |
| GET | `/wallet/balance` | Yes | Current balance |
| GET | `/wallet/transactions` | Yes | Paginated history |

### 9.1 Credit and debit

```
POST /api/v1/wallet/credit
Authorization: Bearer <access token>
Idempotency-Key: 3b241101-e2bb-4255-8caf-4136c566a962
Content-Type: application/json

{ "amount": 500, "description": "Top-up" }
```

Response: `201 Created` for a new entry, `200 OK` for an idempotent replay. The body is identical in both cases.

```
{
  "id": 42,
  "type": "CREDIT",
  "amount": 500,
  "balance_after": 1500,
  "description": "Top-up",
  "created_at": "2026-11-01T10:00:00Z"
}
```

`/wallet/debit` has the same request and response shape with `type` set to `DEBIT`.

### 9.2 Balance

```
GET /api/v1/wallet/balance
200 -> { "balance": 1500, "updated_at": "2026-11-01T10:00:00Z" }
```

### 9.3 History

```
GET /api/v1/wallet/transactions?limit=20&cursor=<opaque>&type=DEBIT
200 -> { "next": "<url or null>", "previous": "<url or null>", "results": [ { entry }, ... ] }
```

- Newest first (ordered by `-id`). Default page size 20, maximum 100.
- Cursor pagination is used instead of offset pagination. With offset, new entries shift the pages and cause duplicates or gaps. A cursor is stable under concurrent inserts and uses the `(wallet, id)` index.
- Optional filter: `type=CREDIT` or `type=DEBIT`.

### 9.4 Registration

```
POST /api/v1/auth/register
{ "username": "ali", "password": "..." }
201 -> { "id": 1, "username": "ali" }
```

## 10. Error Handling

### 10.1 Uniform format

A custom DRF exception handler gives every error the same shape:

```
{
  "error": {
    "code": "insufficient_funds",
    "message": "Insufficient funds.",
    "details": {}
  }
}
```

For validation errors, `details` holds per-field messages, for example `{ "amount": ["A valid integer is required."] }`.

### 10.2 Error catalogue

| HTTP | `code` | When |
| --- | --- | --- |
| 400 | `validation_error` | Invalid body: zero or negative amount, wrong type, description too long |
| 400 | `amount_limit_exceeded` | Amount above `MAX_TRANSACTION_AMOUNT` |
| 400 | `invalid_idempotency_key` | Header missing or not a valid UUID |
| 400 | `username_taken` | Registration with an existing username |
| 401 | `not_authenticated` | Token missing, invalid or expired |
| 404 | `wallet_not_found` | The user has no wallet |
| 409 | `idempotency_conflict` | Same key with a different type or amount |
| 422 | `insufficient_funds` | Debit larger than the balance |
| 422 | `balance_limit_exceeded` | Credit would exceed `MAX_WALLET_BALANCE` |
| 500 | `internal_error` | Unexpected failure; no internal details exposed, full details logged server-side |

### 10.3 Layering of errors

The service layer raises domain exceptions (`InsufficientFunds`, `BalanceLimitExceeded`, `IdempotencyConflict`, `WalletNotFound`) that know nothing about HTTP. The exception handler is the single place that maps them to status codes and `code` values. This keeps services testable without HTTP and keeps the mapping consistent.

## 11. Authentication

The brief did not specify user management, so a small standard JWT flow is implemented with `djangorestframework-simplejwt`.

- **Register:** creates the user and the wallet inside one `transaction.atomic()`. If wallet creation fails, the user is not created. Password rules come from Django's `AUTH_PASSWORD_VALIDATORS`.
- **Login and refresh:** return an access token and a refresh token. `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION` are enabled, so a refresh token can be used once.
- **Logout:** blacklists the supplied refresh token (`rest_framework_simplejwt.token_blacklist`). An invalid token returns 400.
- **Access token lifetime:** short in production (5 to 15 minutes).
- **Wallet creation** lives in the registration service rather than a signal, because signals hide behaviour and are harder to trace and test.

**Known limitations:** an access token stays valid until it expires even after logout, because the blacklist applies to refresh tokens. Users created by other means (`createsuperuser`, Django admin) have no wallet and receive `wallet_not_found`. Verification of e-mail or phone, password reset and rate limiting are out of scope.

## 12. Environments and Configuration

Three fully separated environments: **dev**, **test** and **prod**. Each has its own settings module, its own database service and volume, its own credentials and its own compose file. Staging is listed as future work.

### 12.1 Settings modules

```
config/settings/
  base.py   # shared: apps, DRF, simplejwt, limits
  dev.py    # DEBUG on, verbose logging
  test.py   # fast and isolated
  prod.py   # DEBUG off, security settings
```

The module is chosen with `DJANGO_SETTINGS_MODULE`. Secrets and environment-specific values (`SECRET_KEY`, database credentials, `ALLOWED_HOSTS`) are read only from environment variables, never from code.

| Aspect | dev | test | prod |
| --- | --- | --- | --- |
| `DEBUG` | True | False | False |
| Database | dev Postgres | test Postgres | prod Postgres |
| `SECRET_KEY` | dev value | fixed test value | required from env, no default |
| Access token lifetime | longer, for convenience | default | short |
| HTTPS and `SECURE_*` settings | off | off | on |
| Server | `runserver` | none | `gunicorn` |

If a required production variable is missing, the application must refuse to start with a clear error rather than fall back to an insecure default.

### 12.2 Infrastructure per environment

```
docker-compose.yml        # shared definition (web service)
docker-compose.dev.yml    # db-dev, dedicated volume and port
docker-compose.test.yml   # db-test on tmpfs (fast, disposable)
docker-compose.prod.yml   # db-prod, dedicated volume, DB port not exposed
.env.dev.example  .env.test.example  .env.prod.example
```

- Real `.env` files are git-ignored. Only `.example` files are committed.
- The test database lives on `tmpfs` and is recreated on every run, so tests can never touch dev or prod data.
- Each environment uses a distinct compose project name (`wallet-dev`, `wallet-test`, `wallet-prod`) so volumes and networks never mix.
- In prod the PostgreSQL port is not published; only the web service reaches it over the internal network.

### 12.3 Commands and migrations

```
make dev-up     make dev-down
make test       # starts test DB, runs the suite, tears it down
make prod-up    make prod-down
make verify     # runs verify_ledger for the chosen environment
make lint       # ruff check and ruff format --check
make format     # ruff check --fix and ruff format
make docs       # validates the OpenAPI schema, zero warnings allowed
```

In production, `migrate` is a separate explicit step and is not run automatically on container start, because several instances starting at once could race on migrations. In dev and test it may run automatically.

## 13. API Documentation (Swagger / OpenAPI)

The API is documented by an OpenAPI schema generated from the code and served as Swagger UI, with a concrete example for every request, success response and error.

- **Tool:** `drf-spectacular`.
- **Routes:** `/api/schema/` (OpenAPI file), `/api/docs/` (Swagger UI), `/api/redoc/` (ReDoc, optional).
- **Switch:** `SWAGGER_ENABLED` is on in dev and test and off in prod unless an environment variable turns it on.
- **Per endpoint:** summary, description, tag (`Auth` or `Wallet`), request body and every response, declared with `@extend_schema`.
- **Idempotency header:** `Idempotency-Key` is documented as a required UUID header on credit and debit, with an example value.
- **Authentication:** the JWT bearer scheme is declared, so the Authorize button in Swagger UI works with a real access token.
- **Error envelope:** a shared `ErrorResponseSerializer` describes the `{error: {code, message, details}}` shape.

### 13.1 Documented examples

| Endpoint | Examples |
| --- | --- |
| `POST /auth/register` | request; 201; 400 `username_taken`; 400 `validation_error` |
| `POST /auth/login` | request; 200 with tokens; 401 |
| `POST /auth/refresh`, `POST /auth/logout` | request; 200 or 204; 400 or 401 for an invalid token |
| `POST /wallet/credit` | request; 201 new entry; 200 replay; 400 `validation_error`, `invalid_idempotency_key`, `amount_limit_exceeded`; 401; 404; 409 `idempotency_conflict`; 422 `balance_limit_exceeded` |
| `POST /wallet/debit` | same as credit, with 422 `insufficient_funds` instead of `balance_limit_exceeded` |
| `GET /wallet/balance` | 200; 401; 404 |
| `GET /wallet/transactions` | 200 with a page and cursor; 401; 404 |

### 13.2 Keeping the documentation true

- All example payloads live in one module (`wallet/docs_examples.py`) that both the schema and the tests use.
- `test_api_docs` sends each example request to the real API and checks the documented status code and body shape, so the documentation cannot drift from behaviour.
- CI runs `spectacular --validate --fail-on-warn`; any schema warning fails the build.

## 14. Source Control and Gitflow

Work follows gitflow. Each phase of the implementation plan (section 21) is developed on its own feature branch and merged into `develop` with a merge commit; the result is released through a release branch.

| Branch | Created from | Merges into | Purpose |
| --- | --- | --- | --- |
| `main` | none | none | Released states only, each tagged |
| `develop` | `main` | `release/*` | Integration of finished features |
| `feature/<name>` | `develop` | `develop` | One per implementation phase |
| `release/<version>` | `develop` | `main` and `develop` | Version bump and changelog, no new features |
| `hotfix/<name>` | `main` | `main` and `develop` | Urgent fix after a release |

### 14.1 Rules

- No direct commits to `main` or `develop`, apart from the very first commit on `main`.
- Merges use merge commits (`--no-ff`), never squash or rebase-merge, so the branch structure stays visible in the history.
- Feature branches are kept after merging.
- Commits follow Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`, `refactor:`), one logical change each, with tests in the same branch as the code they cover.
- No force-push and no history rewriting after a merge.
- With a remote, every merge goes through a pull request and CI must pass first. Without one, merge locally after lint and tests pass.

### 14.2 Release

```
git checkout -b release/1.0.0 develop
# bump version, update CHANGELOG.md
git checkout main
git merge --no-ff release/1.0.0
git tag -a v1.0.0 -m "Release 1.0.0"
git checkout develop
git merge --no-ff release/1.0.0
```

The tag triggers the CD workflow (section 16). The final result is reviewed with `git log --graph --oneline --all`.

## 15. Code Quality and Linting (Ruff)

Ruff is the single tool for linting, import sorting and formatting, replacing flake8, isort and Black. The configuration is deliberately small and lives in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["**/migrations/*"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

- `E` and `F` catch style errors and pyflakes issues, `I` sorts imports, `B` finds likely bugs, `UP` flags outdated syntax.
- `make lint` runs `ruff check .` and `ruff format --check .`; `make format` fixes and formats.
- CI runs the same two commands, so local and CI results agree.
- Findings are fixed, not ignored. A `# noqa` must name the rule and give a reason.
- Migrations are excluded because they are generated.

## 16. CI/CD (GitHub Actions)

Every push and pull request is linted and tested, and every version tag builds and publishes a container image. The setup is intentionally simple.

### 16.1 CI (`.github/workflows/ci.yml`)

Triggers: push to `main`, `develop`, `feature/**`, `release/**` and `hotfix/**`; pull requests into `main` and `develop`; and `workflow_call`, so CD can reuse it. A newer run on the same branch cancels the older one.

| Job | Steps | Fails when |
| --- | --- | --- |
| lint | `ruff check`, `ruff format --check` | Any lint or format finding |
| test | PostgreSQL 16 service container, `makemigrations --check`, `spectacular --validate --fail-on-warn`, `pytest` with coverage | A test fails, a migration is missing, the schema has a warning, or coverage is under the threshold |
| docker-build | Build the production image without pushing | The Dockerfile is broken |

- The test settings read the database host and port from environment variables, so the same settings work with the local test compose file and the CI service container.
- Actions are pinned to major versions and workflow permissions are limited to `contents: read`.

### 16.2 CD (`.github/workflows/cd.yml`)

Trigger: a pushed tag matching `v*`.

1. **ci:** reuse the CI workflow. Nothing is published if it fails.
2. **publish:** build the production image and push it to GitHub Container Registry as `ghcr.io/<owner>/<repo>`, tagged with the version and `latest`. It uses the built-in `GITHUB_TOKEN` with `packages: write`.
3. **deploy:** bound to the `production` environment. No deployment target was specified, so this job only prints the intended steps (run the explicit `migrate` step, then roll out the new image). It is a placeholder, not a real deployment.

### 16.3 Manual GitHub settings

These cannot be committed as code and must be set by the repository owner: branch protection on `main` and `develop` requiring the CI checks, and a required reviewer on the `production` environment.

## 17. Project Structure and Layering

```
wallet-service/
  .github/workflows/   ci.yml  cd.yml
  config/
    settings/ (base, dev, test, prod)
    urls.py
  accounts/
    services.py        # register_user: user and wallet, atomic
    serializers.py  views.py  urls.py
  wallet/
    models.py          # Wallet, LedgerEntry, append-only queryset
    services.py        # credit, debit, verify_wallet
    fingerprint.py     # canonical payload and SHA-256
    exceptions.py      # domain exceptions
    docs_examples.py   # examples shared by Swagger and tests
    serializers.py  views.py  urls.py  pagination.py
    management/commands/verify_ledger.py
    tests/
  core/
    exception_handler.py
  requirements/        base.txt  dev.txt
  docs/                analysis.md  DECISIONS.md
  Dockerfile  docker-compose*.yml  .env.*.example
  Makefile  pyproject.toml (ruff, pytest)  CHANGELOG.md  README.md
```

| Layer | Responsibility | Must not |
| --- | --- | --- |
| Serializer | Validate input shape and types | Contain business rules |
| View | Read the header, call the service, serialise output | Contain business logic or queries beyond the service call |
| Service | Business rules, transactions, locking, idempotency | Know about HTTP |
| Model | Data shape and constraints | Contain workflows |
| Exception handler | Map domain errors to HTTP | Decide business outcomes |

## 18. Test Strategy

### 18.1 Tools

`pytest`, `pytest-django`, DRF `APIClient`, `pytest-cov`, and real PostgreSQL from the test compose file. Concurrency tests use threads with `@pytest.mark.django_db(transaction=True)`, because a normal test wraps everything in one transaction and would hide real locking behaviour.

### 18.2 Layout

```
wallet/tests/
  conftest.py  test_models.py  test_services.py  test_idempotency.py
  test_concurrency.py  test_verification.py  test_api_wallet.py
  test_api_auth.py  test_api_docs.py  test_error_format.py
```

### 18.3 Cases

**Models**

- Zero amount, negative balance and duplicate `(wallet, key)` are rejected by the database.
- `save()` on an existing entry, `delete()`, and `QuerySet.update/delete` raise errors.
- Deleting a wallet that has entries is blocked by `PROTECT`.

**Services**

- Successful credit and debit update the balance and create one entry with a correct `balance_after`.
- Debit equal to the balance succeeds and leaves 0.
- Debit above the balance raises `InsufficientFunds`, leaves the balance unchanged and creates **no entry**.
- Credit above `MAX_WALLET_BALANCE` and amount above `MAX_TRANSACTION_AMOUNT` are rejected.
- Atomicity: a simulated failure mid-operation leaves neither an entry nor a balance change.

**Idempotency**

- Same key and payload: one entry, one balance change, identical result.
- Same key with a different amount or type: conflict.
- Same key with a different description: original result returned.
- Retry after an insufficient-funds failure is evaluated again and can succeed.
- Two users with the same key do not interfere.
- The fingerprint is deterministic.

**Concurrency**

- Ten simultaneous debits of 100 on a balance of 500: exactly five succeed, five fail, final balance 0, never negative.
- Ten simultaneous requests with one key: exactly one entry, identical responses.
- Mixed concurrent credits and debits: `verify_wallet` reports a consistent wallet afterwards.
- Threads start together using `threading.Barrier`, tests never rely on `sleep`, and each thread closes its database connection.

**Verification**

- Healthy wallet reports consistent.
- A balance tampered with raw SQL is detected, and so is a broken `balance_after` chain.
- The command reports problems and exits non-zero.

**API and authentication**

- Missing token returns 401; missing or malformed `Idempotency-Key` returns 400.
- Invalid amounts (0, negative, string, float, boolean, null, missing) return 400.
- Replay returns 200 with the original body; insufficient funds returns 422.
- User B can never see user A's entries or balance.
- History is ordered newest first, cursor paging has no duplicates or gaps, `type` filter and the `limit` maximum work.
- Registration creates user and wallet atomically and rolls back both on failure; duplicate username and weak password return 400.
- Refresh rotation invalidates the old refresh token; logout blacklists it.
- Every error has the uniform envelope, and a 500 does not leak internals.

**API documentation**

- `/api/schema/` returns 200 and the schema validates with no warnings.
- Every operation has at least one documented example.
- Each documented example request, sent to the real API, returns the documented status code and body shape.

### 18.4 Principles

- Arrange, Act, Assert, with descriptive names such as `test_debit_exceeding_balance_creates_no_entry`.
- Independent tests with no ordering assumptions.
- Service tests run without HTTP; API tests check only HTTP translation.
- Initial balances are created through the service, never by writing the balance directly, so invariants hold in test data.
- Coverage is reported and enforced with `--cov-fail-under`, but the goal is meaningful tests rather than a number.

## 19. Alternatives Considered and Trade-offs

| Decision | Chosen | Alternative | Reasoning |
| --- | --- | --- | --- |
| Balance storage | Denormalised balance plus ledger, updated atomically | Compute from the ledger on every read; pure event sourcing | Reads stay constant-time and verification proves consistency. Computing on read slows down as history grows. |
| Duplicate detection | `request_fingerprint` column | Compare stored fields directly | The fingerprint is a single cheap comparison and extends if the payload grows. The cost is one column and a normalisation rule. |
| Concurrency control | Pessimistic row lock per wallet | Optimistic version field; atomic `F()` update | Predictable on a hot row with no retry loop. An `F()` update cannot also provide `balance_after` and the idempotency check. |
| Isolation level | `READ COMMITTED` plus lock | `SERIALIZABLE` | Avoids serialisation failures and retry logic. |
| Amount type | Integer minor units | Decimal, float | Exact arithmetic. Float is rejected. |
| Amount input | Strict JSON integer only | DRF default (accepts strings and floats) | Ambiguity is dangerous in a financial API. |
| History paging | Cursor on `-id` | Offset | Stable under concurrent inserts and index friendly. No random page jumps, which history does not need. |
| History ordering | By `id` | By `created_at` | Equal timestamps are ambiguous; ids are monotonic within a wallet. |
| Wallet creation | In the registration service, same transaction | Signal; lazy creation on first use | Explicit and testable. Lazy creation is racy. |
| Error format | Custom envelope | RFC 7807 problem+json | Simpler for this scope and still uniform. |
| Verification | Service function and command | Public endpoint | Operational concern; avoids extra surface and load. |
| Failed requests | Not stored | Store every outcome | Ledger reflects real balance changes only. Failures are cheap to re-evaluate. |
| Limits | Transaction cap and balance cap | One cap | A transaction cap alone cannot bound the balance. |
| Append-only | Application guards, trigger as future work | Database trigger now | Proportionate effort; tampering is detectable by verification. |
| Configuration | Settings modules and env variables | Single settings file | Environment differences stay readable. |
| API documentation | Generated from the code with drf-spectacular | Hand-written OpenAPI file | The schema follows the code and the examples are executed by tests, so the documentation cannot drift. |
| Branching model | Gitflow | Trunk-based development | Requested by the owner. A branch per phase makes the work easy to review. Trunk-based would be lighter for one developer. |
| Continuous delivery | Publish an image, deploy step as a placeholder | A deploy to an invented server | No deployment target was specified. Inventing one would be misleading. |
| Lint and format | ruff only | flake8, isort and Black | One fast tool with one small configuration. |

## 20. Limitations and Future Improvements

**Known limitations**

- Access tokens remain valid until expiry after logout.
- Users created outside registration have no wallet.
- Any authenticated user can credit their own wallet (assumption A4). A real system would put credit behind a payment gateway or an admin role.
- Idempotency keys never expire.
- No database `lock_timeout`, so a stalled transaction can make others wait.
- Writes to a single wallet are serialised by design, which bounds per-wallet throughput.
- Raw SQL can bypass the append-only guards. Verification detects it but does not prevent it.
- No rate limiting.

* Continuous delivery does not deploy anywhere. The deploy job is a placeholder because no target was specified.
* Swagger UI is off in production by default.
* Branch protection and the production approval rule must be configured manually on GitHub.

**Future improvements**

- Transfers between wallets with ordered lock acquisition to avoid deadlocks
- A reversal or refund flow built on compensating entries
- PostgreSQL trigger to enforce append-only at the database level
- `lock_timeout` and `statement_timeout`
- A staging environment
- Observability: structured logs, request ids, metrics, a scheduled `verify_ledger` job with alerting
- Idempotency key retention policy
- Ledger partitioning if volume requires it

* A real deployment job once a deployment target exists

## 21. Implementation Plan

The work is split into eleven phases plus a release. Each phase is a separate feature branch merged into `develop` with a merge commit (section 14), and its tests are written before its code.

| Phase | Branch | Work | Done when |
| --- | --- | --- | --- |
| 1 | `feature/project-scaffolding` | Project, settings modules, Dockerfile, compose files, env examples, Makefile, requirements | `make test` runs an empty suite against the separate test database |
| 2 | `feature/ruff-and-ci` | Ruff configuration, `make lint` and `make format`, `ci.yml` | CI runs lint and tests with the same commands as local |
| 3 | `feature/models-constraints` | `Wallet`, `LedgerEntry`, constraints, append-only queryset, migrations | `test_models` passes |
| 4 | `feature/wallet-services` | Fingerprint, credit and debit, limits, domain exceptions | `test_services` and `test_idempotency` pass |
| 5 | `feature/concurrency-tests` | Threaded tests on real PostgreSQL | `test_concurrency` passes 10 runs in a row |
| 6 | `feature/ledger-verification` | `verify_wallet` and `verify_ledger` command | `test_verification` passes |
| 7 | `feature/wallet-api` | Serializers, views, pagination, exception handler | `test_api_wallet` and `test_error_format` pass |
| 8 | `feature/authentication` | Register, login, refresh, logout, blacklist | `test_api_auth` passes |
| 9 | `feature/api-docs-swagger` | OpenAPI schema, Swagger UI, examples (section 13) | `test_api_docs` passes and the schema validates with zero warnings |
| 10 | `feature/cd-pipeline` | `cd.yml`: image publish and deploy placeholder (section 16) | Workflow is valid and documented |
| 11 | `feature/readme-and-hardening` | README, decisions log, coverage gate, cleanup | A reviewer can run everything with one command and the coverage gate passes |
| Release | `release/1.0.0` | Version bump, changelog, merge into `main`, tag `v1.0.0`, merge back into `develop` | CI is green on `main` and the tag is published |
