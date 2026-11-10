# Contributing

This is a single-developer project, but it follows team-grade practices so it stays maintainable as it grows.

## Workflow

1. Branch from `main`: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`.
2. Commit with [Conventional Commits](https://www.conventionalcommits.org): `feat(voice): add barge-in`, `fix(ui): caption flicker between sentences`.
3. Open a PR. CI must be green: lint, format, types, tests, build, and the docs build.
4. Record significant decisions as an [ADR](docs/adr/index.md).
5. Update `CHANGELOG.md` under **Unreleased**.

## Quality gates

```bash
# TypeScript (repo root)
pnpm format:check && pnpm lint && pnpm typecheck && pnpm test

# Python (services/core)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

Install the git hooks once with `uvx pre-commit install`.

## Engineering principles

- **Dependency rule.** `domain` ← `application` ← `adapters`/`api`. Inner layers never import outer ones. Third-party SDKs live only in adapters.
- **Program to ports.** New capabilities start as a `Protocol` in `domain/ports.py`, with a fake in `tests/fakes.py`.
- **One composition root.** Only `container.py` (backend) and `dashboard/registry.ts` (UI) know concrete implementations.
- **Single responsibility.** Pure logic is kept out of I/O: endpointing, sentence chunking, caption timing and conversation reducers are pure and unit-tested.
- **Fail loudly at the edges, gracefully in the UI.** Adapters raise domain errors (`LanguageModelError`, …) that the session turns into a spoken or visible message.
- **Security by default.** The service binds to loopback, WebSocket origins are allow-listed, the Tauri CSP is strict, and secrets live in `.env` (never committed).

## Documentation standards

- **Python.** Every public module, class and function has a Google-style docstring (enforced by Ruff `D` rules). Docstrings are rendered into the docs site by mkdocstrings.
- **TypeScript.** TSDoc on every exported symbol, with `@example` blocks for non-obvious APIs.
- **Markdown.** Architecture changes update `docs/architecture/*`. New extension points get a guide in `docs/guides/`.

## Adding things

- A widget: [docs/guides/adding-a-widget.md](docs/guides/adding-a-widget.md)
- An AI/speech engine: [docs/guides/adding-an-adapter.md](docs/guides/adding-an-adapter.md)
