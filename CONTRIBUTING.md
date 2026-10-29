# Contributing to MUFFIN.AI

Thanks for your interest. MUFFIN is early-stage, so the most valuable contributions right now are **design feedback, bug reports, and small, well-tested improvements** to the core runtime.

## Before you start

1. Read [`docs/vision.md`](docs/vision.md) and [`docs/architecture.md`](docs/architecture.md).
2. Open an issue describing what you want to change **before** sending a pull request, especially for anything that touches the safety layer or public interfaces.

## Development setup

```bash
git clone https://github.com/<your-username>/MUFFIN.git
cd MUFFIN
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # never commit .env
pytest
python examples/hello_agent.py
```

Requires Python 3.10+. Before opening a PR run `ruff check .`, `mypy` and `pytest` (CI runs all three).

## Project layout

```
src/muffin/      core package (agent SDK, runtime, memory, safety, trace)
tests/           pytest suite
examples/        runnable demos
docs/            vision and architecture
```

The pillar folders (`mathematics/`, `systems/`, `simulation/`, `cognitive-architecture/`, `founder-intelligence/`) hold notes and experiments, not production code.

## Engineering rules

These come straight from the architecture and are enforced in review.

- **Layers talk only to adjacent layers.** No reaching across the stack.
- **Safety is outside the agent's control.** An agent must never be able to disable, modify, or bypass the safety layer.
- **Default deny, fail closed.** Unknown actions are blocked. If a safety check errors, the action is blocked.
- **Every change to behavior needs a test.** Safety mechanisms need a test that proves they *block* something, because a safety mechanism that has not been tested to fail is assumed broken.
- **Everything is explainable.** New runtime behavior must appear in the decision trace.
- **State must be recoverable.** Anything that changes agent state must work with checkpoint and rollback.
- **Keep it small.** Prefer a minimal change with a clear test over a large refactor.

## Pull request checklist

- [ ] Linked to an issue
- [ ] Tests added or updated, and `pytest` passes locally
- [ ] Docs updated if behavior or interfaces changed
- [ ] No secrets, API keys, or generated data committed
- [ ] Safety-related changes explain the threat or failure mode they address

## Commit messages

Short imperative summary, with an optional body explaining *why*:

```
Add rate limit window reset to safety layer

Window entries now expire based on the injected clock so tests
can control time deterministically.
```

## Reporting security issues

If you find a way for an agent to bypass the safety layer, please **do not open a public issue**. Contact the maintainer directly (see the repository profile) with reproduction steps.

## Code style

- Type hints on public functions
- Docstrings on public classes, explaining the *cognitive role* of the component
- Standard library first; add a dependency only with a clear reason
