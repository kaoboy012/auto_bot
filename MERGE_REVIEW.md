# Selective merge review

## Basis

This candidate starts from `timing_source_cleaned.zip`, preserving the dead-code cleanup and per-domain browser rate limits. It selectively adopts maintenance and observability changes from `telegram_giftcode_bot_timing_merged.zip`.

## Adopted

- Batched durable-inbox retention cleanup: delete child work-items before expired parent rows, remove pre-existing orphan items, and release the lock between batches.
- Separate durable-inbox maintenance that checkpoints the WAL around `VACUUM` and reports database size before/after.
- A post-`VACUUM` WAL checkpoint for the primary database.
- Logs for dropped history rows, retry/cleanup failures, database/inbox maintenance failures, and browser input-reload errors.
- Merged archive regression tests, `.gitignore`, and `.env.example` (credential fields were blank in the supplied example).

## Intentionally excluded

- The merged archive's removal of `DOMAIN_RATE_LIMITS` and fallback to one global throttle. The cleaned per-domain limits remain in both `config.py` and `main_script.py`.
- `enqueue_latest_nowait`, which drops the oldest in-memory queued item when full; this can silently lose work and does not fit the durable-ingress model.
- `_kill_all_msedge`, which can terminate unrelated Edge processes, and unused browser helpers (`_detect_result_by_text_diff`, `_respawn_page`).
- The stale `performance_update.patch` and duplicate `task_tracker.py` from the merged archive.
- The merged logger rotation-count change, because it changes configuration semantics without a regression test.

## Verification

- `python3 -m pytest -q`: **18 passed**.
- Python syntax compilation: **24 files, 0 failures**.
- Confirmed per-domain rate-limit config is present and still consumed by `main_script.py`.
- Confirmed no `.env`, Telegram session, SQLite database, or runtime log is included in the package.

These are source-level tests, not a production load test. Before deployment, preserve the separately managed production `.env`, Telegram session files, databases, logs, and browser profile. Back up first, deploy during a controlled window, verify startup, then monitor inbox latency, SQLite errors, per-domain tab waits, and browser resource usage under representative load.
