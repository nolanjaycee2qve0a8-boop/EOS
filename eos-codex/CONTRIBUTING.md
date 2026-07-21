# Contributing to EOS

EOS changes must preserve the architecture specification: the kernel remains
stable, capabilities evolve without modifying kernel architecture, domain
objects are immutable, runtime owns state transitions, and replay remains a
first-class feature.

## Local checks

Use Python 3.12, install the development dependencies, and run:

```bash
ruff check .
ruff format --check .
mypy .
pytest
```

Keep changes focused and accompany future behavior with appropriate unit,
integration, or replay tests.
