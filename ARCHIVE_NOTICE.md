# Clean source archive notice

This archive contains the source code after the confirmed dead-code cleanup and
per-domain rate-limit update.

Excluded intentionally:

- `.env` and all credentials/secrets
- Telegram session files
- SQLite databases
- logs, caches, and `__pycache__`
- `task_tracker.py` (removed as a duplicate module)

Before deployment, copy a separately managed `.env` into the project directory
and verify it has restrictive permissions.
