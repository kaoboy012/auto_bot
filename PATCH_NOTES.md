# AutoBot performance update — source review and safe fixes

## Implemented in the source bundle

- **Telethon-level source filtering:** `NewMessage` and `MessageEdited` builders filter by configured chats when `TELEGRAM_FILTER_AT_SOURCE=true` (default). `quick()` remains a second check; the global `Raw()` probe stays unfiltered.
- **Duplicate ingress task suppression:** reserve identical event fingerprints before allocating background coroutines.
- **Spoiler-aware edits:** include spoiler entity offsets/lengths in in-memory and durable dedup fingerprints. No-spoiler durable hashes remain backward-compatible.
- **Ingress observability:** acceptance logs include `ingress_to_durable_ms`, `ingress_tasks`, and RAM queue depth. Request timing includes queue residence through worker semaphore acquisition and inbox claim.
- **CDP idle-memory correctness:** separate actual `last_used` from memory-maintenance timestamps, so periodic compaction no longer resets the 30-minute reload timer. Skip tabs marked `reserved` in both garbage collection and memory maintenance.
- **SQLite retention correctness:** add an index on `(status, completed_at)`. Retention cleanup now deletes old child work-items before their parent rows and removes orphan work-items from earlier runs.

## Source-level findings and current defaults

- Browser submission defaults are internally aligned: global submit cap 8, per-domain cap 2, and site profiles provide 1 or 2 tab slots. `TAB_POOL_SIZE=2` is a **per-domain** ceiling, not a global tab cap. If all seven built-in browser profiles are active, up to 11 warm tabs may exist while at most 8 submissions run concurrently. The value `MAX_TAB_PER_DOMAIN_CAP=5` is currently above every built-in profile's slot count and is not the effective limit.
- `TAB_POOL_MIN_TABS_PER_DOMAIN=2` plus profile caps of at most 2 means the idle-spare GC generally has no healthy spare tabs to close; current pool behavior favors keeping tabs warm. RAM-vs-latency tuning needs actual Edge resource measurements.
- Both SQLite databases use WAL, `synchronous=NORMAL`, a 10-second busy timeout, one connection protected by a lock, and executor offloading. That is a sound single-writer model; increasing executor worker counts does not create parallel SQLite writes. Inbox ingress is separated from state/maintenance work.
- Inbox rows are retained for 7 days; main submission logs are pruned after 30 days by the daily maintenance job. The child-row cleanup gap is fixed in this version.

## Concurrency tuning status

No production log files or Windows runtime metrics were available in the current Sandbox/upload workspace, and the production `.env` was not read. **No numeric concurrency values were changed by guesswork.** Collect representative `ingress_to_durable_ms`, `ingress_tasks`, `queue=x/max`, request timing stages, SQLite locked/error counts, Edge CPU/RAM, and per-domain tab-acquire wait before changing semaphore or pool limits. `ingress_queue_wait` is retained in the in-memory/dashboard timing path; a JSON timing line is persisted only when verbose timing logging is enabled, so export the dashboard records or enable it briefly for sampling.

## Verification performed

- All Python files pass `py_compile`.
- Pinned Telethon 1.35 event builders pass configured chats and reject unrelated chats.
- Focused spoiler tests cover UTF-16 offsets after astral Unicode, spoiler-only hash changes, unchanged legacy no-spoiler hashes, and duplicate task suppression.
- SQLite integration check verified WAL/NORMAL/busy-timeout settings, retention index, expiry of child+parent rows, orphan cleanup, and preservation of recent rows.
- A fake-clock test verified that memory compaction preserves true last-use time, the 1800-second idle threshold triggers one reload, reload cooldown prevents repeated reloads, and reserved tabs are not touched.
- These are source-level/focused checks, not a production load test or a claim of measured speedup.

## Apply

Back up and replace source files from the sanitized bundle. Do not replace `.env`, Telegram `.session` files, databases, logs, or the Edge profile. After deployment, verify startup and collect at least 30–60 minutes of representative load before tuning concurrency.
