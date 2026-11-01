# Decisions Log

This file records deviations from `docs/analysis.md` and the reasoning behind
them. The analysis document is the source of truth; anything that differs is
listed here.

## Deviations from the analysis

| Date | Area | Deviation | Reason |
| --- | --- | --- | --- |
| 2026-11-02 | Ruff configuration | `extend-exclude` also excludes `**/*.md` | Ruff 0.17 formats Python code blocks inside Markdown. The analysis document must stay untouched, so Markdown is excluded from formatting. |
