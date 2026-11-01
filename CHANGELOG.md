# Changelog

All notable changes to this project are documented here.

## [1.0.0] - 2026-11-02

First public release.

### Added

- Django project with separate dev, test and prod settings modules and Docker
  Compose environments (test database on `tmpfs`, prod without a published
  database port).
- `Wallet` and append-only `LedgerEntry` models with database CHECK
  constraints, a per-wallet idempotency unique constraint and append-only
  guards.
- Credit and debit services with per-wallet row locking, configurable
  transaction and balance limits, and SHA-256 request fingerprints.
- Idempotent retries: replay returns the original entry; conflicting reuse of a
  key returns `409`.
- Threaded concurrency tests proving no negative balance and one entry per
  idempotency key on real PostgreSQL.
- `verify_wallet()` and the `verify_ledger` management command.
- Wallet API with strict integer validation, cursor pagination and a uniform
  error envelope.
- JWT registration, login, refresh rotation and logout with token blacklisting.
- OpenAPI schema, Swagger UI and ReDoc with executable examples for every
  endpoint.
- Ruff configuration, GitHub Actions CI and tag-triggered CD with a documented
  deploy placeholder.
- README, decisions log and coverage gate.
