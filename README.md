# EOS — Energy Operating System

*An Open Architecture for Explainable Energy Decision Systems*

EOS is the reference implementation of an Energy Decision Kernel. It provides
an engineering foundation for stable kernel architecture, evolving
capabilities, immutable domain objects, runtime-owned state transitions, and
first-class replay.

This repository currently contains only the initial project skeleton. It does
not implement energy-management algorithms.

## Development

EOS requires Python 3.12.

```bash
python -m pip install -e ".[dev]"
pre-commit install
ruff check .
ruff format --check .
mypy .
pytest
```
