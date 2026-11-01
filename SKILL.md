---
name: wallet-ledger-implementation
description: Implements the Wallet & Ledger service (Django, DRF, PostgreSQL) phase by phase from the analysis document in docs/analysis.md, using gitflow branches, Swagger/OpenAPI docs with examples, ruff, and GitHub Actions CI/CD. Use this skill whenever the user asks to build, continue, review, test or fix the wallet service, ledger, credit/debit endpoints, idempotency, balance verification, or mentions the wallet interview task or the analysis document, even if they do not name this skill.
---

# Wallet & Ledger Service: Implementation Skill

You are implementing a small but production-minded wallet service. The design has already been analysed and decided together with the owner. Your job is to implement it faithfully, in small verified steps, with a clean git history that a reviewer can read.

The owner will present this work in a job interview and must be able to defend every decision. So: no surprises, no unexplained choices, no claims you have not verified.

## 0. Before writing any code

1. Read `docs/analysis.md` completely. It is the source of truth. If it is missing, stop and ask the user to place the exported analysis document at `docs/analysis.md`.
2. Read this skill completely.
3. Check the environment: `git --version`, `python --version` (3.12 expected), whether Docker and PostgreSQL are available, whether a git remote `origin` exists, whether `gh` is installed. Remember the results; they decide how you merge (section 4) and what you can honestly claim (section 11).

## 1. Source of truth and deviations

- If this skill and `docs/analysis.md` disagree on a design decision, the analysis document wins. For the extra requirements (Swagger, gitflow, ruff, CI/CD) this skill wins, because the document does not cover them.
- Do not silently deviate. If something in the document is impossible or clearly wrong, make the smallest reasonable change, and record it in `docs/DECISIONS.md` under "Deviations from the analysis" with the reason. Mention it in your phase report.
- Do not ask the user about anything the document already decides. Ask only about things that are truly missing (for example the GitHub repository name) or about a conflict you cannot resolve.

## 2. Decisions you must not change (summary)

The document has the details. These are the points most likely to be gotten wrong:

- Stack: Python 3.12, Django, DRF, PostgreSQL. Never SQLite, not even for tests.
- Amounts are integers in minor units (`PositiveBigIntegerField`). `amount` input is strict: JSON integer only; reject strings, floats, booleans, null, zero and negatives.
- `Wallet`: one per user, `balance` denormalised, `CHECK (balance >= 0)`.
- `LedgerEntry`: append-only; `type`, `amount`, `balance_after`, `idempotency_key` (UUID), `request_fingerprint` (SHA-256 hex), `description` (max 255), `created_at`. Constraints: `amount > 0`, `balance_after >= 0`, valid type, `UNIQUE (wallet, idempotency_key)`. Index `(wallet, id)`. `on_delete=PROTECT`. Application-level guards block `save()` on existing rows, `delete()`, and queryset `update()` and `delete()`.
- Fingerprint: SHA-256 of canonical JSON of `type` and `amount` only (sorted keys, compact separators). `description` is deliberately excluded.
- Service flow: `transaction.atomic()` then `select_for_update()` on the wallet row, then idempotency lookup inside the lock, then business checks, then insert entry, then update balance. Isolation stays at `READ COMMITTED`. Never use `SERIALIZABLE`.
- Idempotency responses: first success 201; replay with the same key and the same fingerprint 200 with the original body; same key with a different fingerprint 409 `idempotency_conflict`. Only successful requests are stored. A failed request is evaluated again on retry.
- Limits from settings: `MAX_TRANSACTION_AMOUNT` and `MAX_WALLET_BALANCE`. Transaction cap exceeded: 400 `amount_limit_exceeded`. Balance cap exceeded: 422 `balance_limit_exceeded`. Insufficient funds: 422 `insufficient_funds`.
- Endpoints under `/api/v1/`: `auth/register`, `auth/login`, `auth/refresh`, `auth/logout`, `wallet/credit`, `wallet/debit`, `wallet/balance`, `wallet/transactions`. No user id in URLs. `Idempotency-Key` header is required and must be a valid UUID.
- Errors always use `{"error": {"code", "message", "details"}}` through one exception handler. Services raise domain exceptions that know nothing about HTTP. A 500 never leaks internals.
- History: cursor pagination ordered by `-id`, default 20, maximum 100, optional `type` filter.
- Auth: `djangorestframework-simplejwt` with refresh rotation and blacklist. Registration creates user and wallet in one transaction (in the service, not a signal). Logout blacklists the refresh token.
- Verification: `verify_wallet()` in the service and `manage.py verify_ledger`. No public verification endpoint.
- Environments: dev, test, prod. Settings modules `base`, `dev`, `test`, `prod`. Secrets only from environment variables. One compose file per environment, each with its own database, volume, credentials and compose project name. Test DB on tmpfs. Prod does not publish the DB port. Prod must refuse to start if required variables are missing. Prod `migrate` is an explicit step.

## 3. Working method

Work in the phases of section 5. For every phase:

1. Create the branch (section 4).
2. Write the tests for the phase first, taken from the test list in the analysis document (section 14 of it). Watch them fail for the right reason.
3. Implement until they pass. Commit in small logical commits with Conventional Commit messages.
4. Run the full quality gate: `make lint`, `make test`. Fix everything. Never weaken, skip or delete a test to make it pass. If a test reveals a design flaw, fix the design and note it in `docs/DECISIONS.md`.
5. Merge into `develop` (section 4).
6. Write a short phase report to the user (section 11).

Concurrency tests (phase 5) must run against real PostgreSQL with `transaction=True`, use `threading.Barrier`, never `sleep`, and close each thread's DB connection. Before merging that branch, run them at least 10 times in a row to prove they are not flaky.

## 4. Gitflow

Branch model:

- `main`: only released, tagged states.
- `develop`: integration branch; every finished feature lands here.
- `feature/<name>`: one branch per phase, created from `develop`.
- `release/<version>`: created from `develop` at the end.
- `hotfix/<name>`: only if a defect is found after the release; created from `main`, merged into both `main` and `develop`.

Setup (once):

```bash
git init -b main
# first commit on main: .gitignore, README skeleton, docs/analysis.md
git checkout -b develop
```

Per phase:

```bash
git checkout develop
git checkout -b feature/<name>
# ... small commits ...
```

Merging a feature (always a merge commit so the branch structure stays visible; never squash, never rebase-merge):

- If a remote `origin` exists and `gh` works: push the branch, open a pull request into `develop`, wait for CI to pass, then merge with a merge commit (`gh pr merge --merge`).
- Otherwise merge locally:

```bash
git checkout develop
git merge --no-ff feature/<name> -m "Merge feature/<name> into develop"
```

Release (once, after all phases):

```bash
git checkout -b release/1.0.0 develop
# bump version, update CHANGELOG.md, no new features
git checkout main
git merge --no-ff release/1.0.0 -m "Release 1.0.0"
git tag -a v1.0.0 -m "Release 1.0.0"
git checkout develop
git merge --no-ff release/1.0.0 -m "Merge release/1.0.0 back into develop"
```

With a remote, do the `release/1.0.0` into `main` merge through a pull request as well, then tag.

Rules:

- Never commit directly to `main` or `develop`, except the very first commit on `main`.
- Never force-push. Never rewrite history that has been merged.
- Do not delete feature branches after merging unless the user asks; the branch list is part of what the reviewer sees.
- Commit messages follow Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`, `refactor:`. One logical change per commit; tests live in the same branch as the code they cover.
- Before every merge: `ruff check`, `ruff format --check` and the test suite must pass.
- At the end show the user `git log --graph --oneline --all` so they can see the structure.

## 5. Phases and branches

| # | Branch | Work | Done when |
|---|---|---|---|
| 1 | `feature/project-scaffolding` | Django project, `config/settings/{base,dev,test,prod}.py`, `Dockerfile` (python:3.12-slim, non-root user, gunicorn), compose files per environment, `.env.*.example`, `.gitignore`, `Makefile`, `requirements/`, pytest config | `make test` runs an empty suite against the separate test DB |
| 2 | `feature/ruff-and-ci` | Ruff config, `make lint` and `make format`, CI workflow (section 8) | CI workflow is valid and runs lint and tests locally the same way |
| 3 | `feature/models-constraints` | `Wallet`, `LedgerEntry`, constraints, append-only guards, migrations | `test_models` passes |
| 4 | `feature/wallet-services` | Fingerprint, `credit`, `debit`, limits, domain exceptions | `test_services` and `test_idempotency` pass |
| 5 | `feature/concurrency-tests` | Threaded tests proving no negative balance and one entry per key | `test_concurrency` passes 10 runs in a row |
| 6 | `feature/ledger-verification` | `verify_wallet`, `verify_ledger` command | `test_verification` passes |
| 7 | `feature/wallet-api` | Serializers, views, pagination, exception handler | `test_api_wallet` and `test_error_format` pass |
| 8 | `feature/authentication` | Register, login, refresh, logout, blacklist | `test_api_auth` passes |
| 9 | `feature/api-docs-swagger` | OpenAPI schema and Swagger UI with examples (section 6) | `test_api_docs` passes, schema validates with zero warnings |
| 10 | `feature/cd-pipeline` | Tag-triggered image build and publish workflow (section 8) | Workflow file is valid and documented |
| 11 | `feature/readme-and-hardening` | README, `docs/DECISIONS.md`, coverage gate, final cleanups | Section 12 checklist passes |

The phases map to section 17 of the analysis document. Keep the order, because later phases depend on earlier ones.

## 6. Swagger / OpenAPI documentation

Use `drf-spectacular`.

- Settings: `DEFAULT_SCHEMA_CLASS` set to spectacular's `AutoSchema`. `SPECTACULAR_SETTINGS` with title, version, and a description that explains the idempotency contract and the error envelope in plain words.
- Routes: `/api/schema/` (OpenAPI file), `/api/docs/` (Swagger UI), `/api/redoc/` (optional ReDoc). Controlled by a `SWAGGER_ENABLED` setting: on in dev and test, off in prod unless the environment variable enables it.
- Every endpoint is documented with `@extend_schema`: summary, description, tag (`Auth` or `Wallet`), request, and responses.
- Every endpoint has **examples** (`OpenApiExample`):
  - Request examples (credit, debit, register, login).
  - Success responses: 201 for a new entry and 200 for an idempotent replay (two separate named examples).
  - One example for every error in the catalogue that the endpoint can return: 400 `validation_error`, 400 `invalid_idempotency_key`, 400 `amount_limit_exceeded`, 401, 404 `wallet_not_found`, 409 `idempotency_conflict`, 422 `insufficient_funds`, 422 `balance_limit_exceeded`.
  - A paginated example for the history endpoint.
- `Idempotency-Key` is documented as a required header parameter (`OpenApiParameter`, location header, type UUID, with an example value) on credit and debit.
- The JWT bearer scheme must appear so that the "Authorize" button works in Swagger UI.
- Define an `ErrorResponseSerializer` for the error envelope and reference it in the error responses.
- Keep all example payloads in one module (for example `wallet/docs_examples.py`) and reuse them in tests: `test_api_docs.py` sends the example requests to the real API and checks that the status code and body shape match what the docs claim. Documentation that can drift from behaviour is a defect.
- Quality gate: `python manage.py spectacular --validate --fail-on-warn --file /dev/null` must pass locally and in CI. Also test that `/api/schema/` returns 200 and that every operation has at least one example.

## 7. Ruff (keep it simple)

Single `pyproject.toml` section, no plugin zoo:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["**/migrations/*"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

- Use `ruff check` for linting (with import sorting through `I`) and `ruff format` for formatting. Do not add Black, isort or flake8.
- `make lint` runs `ruff check .` and `ruff format --check .`. `make format` runs `ruff check --fix .` and `ruff format .`.
- Fix findings instead of ignoring rules. Any `# noqa` must name the rule and carry a short reason.
- Pre-commit hooks are optional; do not add them unless the user asks.

## 8. CI/CD with GitHub Actions (keep it simple)

### `.github/workflows/ci.yml`

- Triggers: `push` on `main`, `develop`, `feature/**`, `release/**`, `hotfix/**`; `pull_request` into `main` and `develop`; and `workflow_call` so the CD workflow can reuse it.
- `concurrency` group per ref with `cancel-in-progress` for non-main branches.
- Job `lint`: checkout, setup Python 3.12 with pip cache, install `requirements/dev.txt`, run `ruff check .` and `ruff format --check .`.
- Job `test`: a `postgres:16` service container with a health check; set `DJANGO_SETTINGS_MODULE=config.settings.test` and the DB variables through `env`; steps: checkout, setup Python with pip cache, install `requirements/dev.txt`, `python manage.py makemigrations --check --dry-run`, `python manage.py spectacular --validate --fail-on-warn --file /dev/null`, then `pytest` with coverage and the `--cov-fail-under` threshold.
- Job `docker-build`: build the production image without pushing, to catch Dockerfile breakage.
- Pin action versions (for example `actions/checkout@v4`, `actions/setup-python@v5`). Use minimal `permissions` (`contents: read`).
- The test settings must read DB host and port from environment variables so the same settings work with the local test compose file and with the CI service container.

### `.github/workflows/cd.yml`

- Trigger: push of tags matching `v*`.
- Job 1: call `ci.yml` (`uses: ./.github/workflows/ci.yml`).
- Job 2 (needs job 1): build the production image and push it to GitHub Container Registry (`ghcr.io/<owner>/<repo>`) using `docker/login-action` with `GITHUB_TOKEN`, `docker/metadata-action` for tags (version and `latest`), and `docker/build-push-action`. Permissions: `contents: read`, `packages: write`.
- Job 3 (needs job 2): deploy placeholder bound to `environment: production`. No deployment target was specified, so this job only prints what a real deploy would do (run the explicit `migrate` step, then roll out the new image). Do not invent servers, secrets or hostnames.
- Tell the user, in the README and in your final report, the settings they must do by hand on GitHub: branch protection for `main` and `develop` requiring the CI checks, and a required reviewer on the `production` environment.

## 9. Dependencies and files

- `requirements/base.txt`: Django (current LTS), djangorestframework, djangorestframework-simplejwt, drf-spectacular, psycopg (binary), gunicorn.
- `requirements/dev.txt`: includes base, plus pytest, pytest-django, pytest-cov, ruff.
- Pin the exact versions you actually installed and tested with. Do not guess version numbers.
- Read environment variables with a small helper in `base.py` (no extra dependency needed). A missing required variable raises `ImproperlyConfigured` with a clear message; `prod.py` has no default for `SECRET_KEY` or DB credentials.
- Commit only `.env.*.example` files. Real `.env` files are git-ignored. Never commit a secret.
- Required files at the end: `README.md`, `CHANGELOG.md`, `docs/analysis.md`, `docs/DECISIONS.md`, `Makefile`, `Dockerfile`, all compose files, `.github/workflows/ci.yml`, `.github/workflows/cd.yml`, `pyproject.toml`.

## 10. Code quality rules

- Layers as in the analysis document: serializers validate shape, views are thin, services hold business rules and transactions, exception handler maps domain errors to HTTP. No business logic in views or serializers. No HTTP concepts in services.
- Type hints on service functions. A short docstring on each service stating its invariants and what it raises.
- `transaction.atomic()` only in the service layer.
- No `float` anywhere near money. No bare `except`. No swallowed exceptions. No `print`; use `logging`.
- Do not catch `IntegrityError` broadly; handle only the idempotency unique violation, outside the failed transaction, as the document describes.
- Tests follow Arrange, Act, Assert, have descriptive names, are independent, and build initial balances through the service, never by writing `balance` directly.
- Prefer small functions and clear names over comments. Comment only the reasons behind non-obvious decisions (locking, fingerprint, ordering).

## 11. Honest reporting

After each phase, give the user a short report:

- Branch name and what was done, in two or three sentences.
- The real output summary of `make lint` and `make test` (counts of passed tests, coverage number). Only report what you actually ran.
- Any deviation from the analysis document (and the entry in `docs/DECISIONS.md`).
- What comes next.

If you cannot run something (no Docker, no PostgreSQL, no network), say so explicitly and say which claims are therefore unverified. In particular, never claim the concurrency tests pass unless they ran against real PostgreSQL. Never invent command output, test results, coverage numbers or CI status.

## 12. Final checklist (phase 11 and before the release)

- [ ] Every requirement in section 3 of the analysis document is covered by an implementation and a named test.
- [ ] `make lint`, `make test` and the schema validation pass from a clean checkout.
- [ ] Concurrency tests passed 10 consecutive runs on PostgreSQL.
- [ ] `verify_ledger` reports a healthy database after the test scenarios.
- [ ] Swagger UI works at `/api/docs/`, every endpoint has examples, and `Authorize` works with a real token.
- [ ] Dev, test and prod each start with their own database; the prod settings fail fast without required variables; no secret is committed.
- [ ] CI is green on `develop` and `main`; the CD workflow file is valid.
- [ ] `git log --graph --oneline --all` shows `main`, `develop`, all feature branches merged with merge commits, the release branch, and the `v1.0.0` tag.
- [ ] README explains: what the service does, assumptions, how to run each environment, how to run tests, Swagger URL, branching model, CI/CD overview, known limitations, and the manual GitHub settings.
- [ ] `docs/DECISIONS.md` lists every deviation from the analysis document (or states that there were none).
- [ ] The final message to the user lists what is done, what is unverified, and 5 to 8 likely interview questions about the design with one-sentence answers.
