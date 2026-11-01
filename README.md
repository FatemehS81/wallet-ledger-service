# Wallet & Ledger Service

A small, production-minded wallet service built with Django, Django REST
Framework and PostgreSQL. Each user owns one wallet; credits and debits are
recorded in an append-only ledger and the current balance can always be
verified from that ledger.

The full analysis and design is in [`docs/analysis.md`](docs/analysis.md).

## Status

Work in progress.
