# 0008. SQLite via the standard library, with versioned migrations

- Status: Accepted
- Date: 2026-11-10

## Context

Tasks, reminders, memories and the document index need durable storage. The data is personal-scale (thousands of rows at most) and single-user. The future mobile apps will sync through the core's REST API, not through the database directly. The original blueprint suggested SQLAlchemy and Alembic.

## Decision

- One SQLite file at `~/.jarvis-os/jarvis.db`, opened with Python's built-in `sqlite3` in WAL mode.
- `Database.run(fn)` executes queries in a worker thread behind a lock, so the event loop never blocks.
- **Migrations** are an ordered tuple of SQL scripts. `PRAGMA user_version` records how many have run, and new ones are appended, never edited.
- Repositories implement the domain ports (`TaskRepository`, `ReminderRepository`, `MemoryStore`). Timestamps are stored as UTC ISO-8601 strings, so they sort correctly.
- Embeddings are stored as float32 BLOBs and searched by brute-force cosine similarity in NumPy. There is no vector extension or database.

## Consequences

- **+** Zero extra dependencies. The file is inspectable with any SQLite browser and easy to back up.
- **+** Tests run against `Database(":memory:")` with the real SQL.
- **−** Hand-written SQL and mapping code. That's acceptable for four tables. Revisit (SQLAlchemy, or `sqlite-vec` for vectors) if the schema or memory size grows by orders of magnitude.
