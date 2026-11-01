# Decisions Log

This file records deviations from `docs/analysis.md` and the reasoning behind
them. The analysis document is the source of truth; anything that differs is
listed here.

## Deviations from the analysis

| Date | Area | Deviation | Reason |
| --- | --- | --- | --- |
| 2026-11-02 | Ruff configuration | `extend-exclude` also excludes `**/*.md` | Ruff 0.17 formats Python code blocks inside Markdown. The analysis document must stay untouched, so Markdown is excluded from formatting. |
| 2026-11-02 | Docker test image | The `Dockerfile` accepts a `REQUIREMENTS` build argument; the test compose file builds with `requirements/dev.txt`, production with `requirements/base.txt` | The production image stays minimal while the test image can run pytest and ruff without a second Dockerfile. |
| 2026-11-02 | Local test workflow | The test compose file publishes the test database on host port `5433` | Allows a fast local pytest loop from a virtualenv; the `make test` path still runs entirely inside the isolated compose project and no dev/prod data is reachable. |
| 2026-11-02 | Logout response | Logout uses SimpleJWT's `TokenBlacklistView` and returns `200` | The analysis explicitly allows `200` or `204`; reusing the library view avoids custom token handling. |
| 2026-11-02 | Coverage gate | `--cov-fail-under=90` with tests and migrations omitted from measurement | The analysis requires a coverage gate but does not name a threshold. 90% is high enough to be meaningful without rewarding trivial test-only lines. |
| 2026-11-02 | Repository contents | `SKILL.md` and the original analysis export are also committed at the repository root | They are the input material for this implementation and keeping them makes the process reviewable. The canonical copy remains `docs/analysis.md`. |

## Notes that are not deviations

- Django is pinned to the current LTS line (5.2.x) as required by the analysis.
- Python 3.12 is used by the Docker image and by the local virtualenv.
- Production migrations are explicit (`make migrate`), never automatic.
- The concurrency tests were run 10 consecutive times against PostgreSQL 16 and
  passed each time.
