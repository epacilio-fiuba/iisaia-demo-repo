# Bulk CSV import for admin users

Status: design approved, pending implementation plan
Date: 2026-05-24

## Goal

Allow an admin (holder of the existing `DEMO_BEARER_TOKEN`) to bulk-import
users or posts from a CSV file. The feature must demonstrate clear handling of
invalid rows, duplicates, and rollback, and must be usable from a small admin
page in the frontend.

## Non-goals

- New role system. The current single bearer token counts as admin.
- Persistent storage. The in-memory store remains the source of truth; the
  rollback story is honest about being an in-memory snapshot/restore, not a DB
  transaction.
- Frontend test runner. The admin UI is verified manually.
- Async concurrency. Handlers stay sync; the GIL serializes them and we don't
  introduce a snapshot race.

## Architecture

```
backend/
  routers/
    imports.py            # NEW — POST /import/{resource}
  services/
    __init__.py           # NEW
    csv_import.py         # NEW — orchestrator + per-resource adapters
  db/client.py            # +snapshot/restore, +email and (title,author_id,body) indexes
  schemas/models.py       # +ImportResult, +ImportInserted, +ImportRowError
  main.py                 # include imports router
frontend/
  admin.html              # NEW
  admin.js                # NEW
  styles.css              # +summary/table/banner styles
  index.html              # +footer link to admin.html
tests/
  conftest.py             # NEW — moves the autouse reset_store fixture here
  test_imports.py         # NEW
scripts/export_openapi.py # run at the end to regenerate openapi.yaml
```

Responsibilities:

- `routers/imports.py` — HTTP only. Parses `multipart/form-data` (file + mode),
  calls the service, maps its result to status + JSON body. Depends on
  `require_bearer`.
- `services/csv_import.py` — FastAPI-agnostic. Exposes
  `run_import(resource, csv_bytes, mode, store) -> ImportResult`. Internally
  two adapters (`UserAdapter`, `PostAdapter`) implement `required_columns`,
  `validate_row(row) -> Model | RowError`, `dup_key(model)`,
  `insert(store, model)`. The orchestrator snapshots the store, walks rows
  (validate → in-CSV dedup → store dedup → insert), and restores on rollback.
- `db/client.py` — adds `snapshot()` / `restore(snap)` and two indexes kept in
  sync by `create_user` / `create_post` so dedup is O(1) and works regardless
  of how the record was created.

## HTTP contract

```
POST /import/{resource}            resource ∈ {users, posts}
Headers:
  Authorization: Bearer <token>
  Content-Type: multipart/form-data
Form fields:
  file:  UTF-8 .csv with header row
  mode:  "atomic" (default) | "partial"
```

Required CSV headers:

- `users` → `name,email`
- `posts` → `title,body,author_id`

Extra columns are ignored. Missing columns → `400 missing column <x>`
(file-level error, not row-level).

Limits:

- File size ≤ 1 MB. Larger → `413`.
- Rows ≤ 1000. Larger → `413`.
- Empty file or zero data rows → `400 empty csv`.

Success response (200):

```json
{
  "resource": "users",
  "mode": "atomic",
  "total_rows": 5,
  "inserted": [
    {"row": 2, "id": 12},
    {"row": 4, "id": 13}
  ],
  "skipped": [
    {"row": 3, "reason": "duplicate_in_store", "detail": "alice@x.com already exists"},
    {"row": 5, "reason": "invalid_field",      "detail": "email: field required"}
  ],
  "rolled_back": false
}
```

Status code rules:

- `mode=partial` → always 200. `inserted` and `skipped` populated as the walk
  produced them. `rolled_back: false`.
- `mode=atomic` with zero errors → 200, `rolled_back: false`.
- `mode=atomic` with ≥1 error → **422**, `inserted: []`, `skipped` lists ALL
  bad rows (do not short-circuit on the first), `rolled_back: true`. 422 over
  200 because nothing was persisted; returning 200 would be a footgun for any
  client/middleware that only checks the status code.

Closed set of `reason` codes:

- `missing_field` — required column empty
- `invalid_field` — Pydantic validation failure (includes malformed email)
- `duplicate_in_csv` — row collides with an earlier row in the same file
  (first wins, rest reported)
- `duplicate_in_store` — already exists in the store
- `author_not_found` — posts only, `author_id` does not exist in the store

Errors that do NOT enter the result body (they are request-level errors):

- 401 missing bearer, 403 invalid bearer (reuses `require_bearer`)
- 400 missing column / unparseable CSV / empty CSV / unknown `mode`
- 404 unknown `resource` (FastAPI Path validation)
- 413 size or row limit exceeded

The `detail` field never contains the bearer token or any header value.

## Data model and dedup

New schemas (in `backend/schemas/models.py`):

```python
class ImportRowError(BaseModel):
    row: int
    reason: Literal[
        "missing_field", "invalid_field",
        "duplicate_in_csv", "duplicate_in_store",
        "author_not_found",
    ]
    detail: str

class ImportInserted(BaseModel):
    row: int
    id: int

class ImportResult(BaseModel):
    resource: Literal["users", "posts"]
    mode: Literal["atomic", "partial"]
    total_rows: int
    inserted: list[ImportInserted]
    skipped: list[ImportRowError]
    rolled_back: bool
```

`User`, `Post`, `UserCreate`, `PostCreate` are not touched.

Row numbering: header is line 1, first data row is line 2. This matches what a
human opening the file in a text editor or spreadsheet will see.

Store changes (`backend/db/client.py`):

- Add `_users_by_email: dict[str, int]` and
  `_posts_by_key: dict[tuple[str, int, str], int]`. Both are kept in sync by
  `create_user` / `create_post` so endpoints that already create records also
  populate the indexes.
- Add `find_user_by_email(email)` and
  `find_post_by_content(title, author_id, body)` returning the existing id or
  `None`.
- Add `snapshot() -> dict` returning shallow copies of `users`, `posts`,
  `_user_seq`, `_post_seq`, `_users_by_email`, `_posts_by_key`.
- Add `restore(snap)` reassigning all six fields.

Snapshots are shallow because `User` and `Post` are pydantic models and we
never mutate them in place. If a future change mutates a model, snapshot
isolation would break — a dedicated test (`test_csv_import_service_snapshot_isolation`)
guards against that.

Dedup walk (two passes over the rows):

1. Validate and parse every row → list of `(row_n, model | RowError)`.
2. Walk the parsed rows. For each valid model, compute `dup_key`:
   - If the key is already in a local set of keys seen this run →
     `duplicate_in_csv`, first wins.
   - Else check `find_*` on the store → `duplicate_in_store` if present.
   - For posts, also check `author_id in store.users` → `author_not_found`.
   - Else insert and add the key to the local set.

In `mode=atomic`, the walk still visits every row (so all errors are
reported), but if any error was collected the store is restored from the
snapshot taken at the start of the request and `inserted` is cleared before
returning.

## Frontend

`frontend/admin.html` — standalone page, same CSS as the rest of the site.
Sections, top to bottom:

- Bearer token input (password-style field; not logged, not put in URLs).
- Resource radio: users / posts.
- File input (accept=".csv").
- Mode radio: atomic (default) / partial, with a one-line caption explaining
  the difference.
- "Importar" button.
- Result panel: summary line + two tables (Inserted: row, id; Skipped: row,
  reason, detail). A red banner appears when `rolled_back: true`.

`frontend/admin.js` — vanilla, no dependencies.

- Reads the four inputs. Client-side checks: file present, ends in `.csv`,
  size ≤ 1 MB. Failing any → inline error, no fetch.
- `POST /import/{resource}` with `FormData(file, mode)` and
  `Authorization: Bearer <token>`.
- UI states: idle, loading (button disabled, "Importando…"), success (200),
  rolled_back (422 with valid result body), error (401/403/400/413/network —
  banner with `detail` or generic message).
- Token storage: `sessionStorage` so it survives a reload but not a tab close.
  Never written to `localStorage`, never logged.
- Result panel is replaced on each new run; no auto-clear timer.

`frontend/index.html` gets a small footer link `<a href="admin.html">Admin</a>`.

`frontend/styles.css` — adds `.import-summary`, `.import-table`,
`.banner-error`, `.banner-warn`. Reuses the existing spacing scale
(4/8/12/16/24/32).

## Tests

`tests/conftest.py` (new) — moves the autouse `reset_store` fixture out of the
individual `test_*.py` files and updates it to clear the two new indexes as
well. The fixtures inside `test_users.py` and `test_posts.py` are removed.
Without this, the existing tests would contaminate each other once the
indexes exist; that's why it counts as required scope, not a tangential
refactor.

`tests/test_imports.py` (new) — cases by intent:

Auth and request shape:

- `test_import_requires_auth` — no bearer → 401.
- `test_import_invalid_resource` — `POST /import/widgets` → 404.
- `test_import_missing_file` — multipart without file → 422.
- `test_import_missing_column` — users CSV without `email` → 400.
- `test_import_too_many_rows` — 1001 rows → 413.
- `test_import_file_too_large` — file > 1 MB → 413.
- `test_import_empty_csv` — headers only, no data → 400.

Happy paths:

- `test_import_users_atomic_ok` — 3 valid rows, atomic → 200, all inserted;
  `GET /users` returns 3.
- `test_import_posts_atomic_ok` — pre-insert one user, import 2 posts → 200,
  both inserted.

Partial mode (store keeps the good rows):

- `test_import_users_partial_with_invalid` — valid, malformed email, valid →
  200, 2 inserted, 1 skipped (`invalid_field`).
- `test_import_users_partial_dup_in_csv` — same email twice → 200, first
  inserted, second skipped (`duplicate_in_csv`).
- `test_import_users_partial_dup_in_store` — pre-insert Ana, then import a
  CSV with Ana → 200, skipped (`duplicate_in_store`).
- `test_import_posts_partial_author_not_found` — row with `author_id=999` →
  skipped (`author_not_found`).

Atomic mode (rollback effective — the case the user wants to see):

- `test_import_atomic_rolls_back_on_invalid` — valid, invalid, valid →
  **422**, `inserted: []`, `skipped` len 1, `rolled_back: true`,
  `GET /users` returns `[]`, `store._user_seq == 0` (the sequence is
  restored too).
- `test_import_atomic_rolls_back_on_dup` — pre-insert Ana, atomic with Ana →
  422, store still has only the original Ana with id=1.
- `test_import_atomic_reports_all_errors` — 5 rows, 3 bad → 422, `skipped`
  len 3 (walk does not short-circuit).
- `test_import_atomic_preserves_preexisting_data` — store has 2 users and 1
  post → atomic import fails → original 2 users and 1 post still there with
  the same ids.

Service-level (no HTTP):

- `test_csv_import_service_user_adapter_validates` —
  `UserAdapter.validate_row({"name": "", "email": "x"})` returns a
  `RowError(missing_field)`.
- `test_csv_import_service_snapshot_isolation` — take a snapshot, mutate the
  store, restore, assert exact equality including `_seq` counters.

Manual verification (not automated):

- Open `frontend/admin.html` against a running backend, paste the bearer
  token, upload a CSV that mixes valid + invalid + duplicate rows in atomic
  mode → red rollback banner, skipped table populated, `GET /users`
  unchanged. Switch to partial mode → green summary, only invalid/dup rows
  skipped, valid ones present.

Final step in the plan:
`uv run python scripts/export_openapi.py` and commit `openapi.yaml` in the
same PR (required by `.claude/rules/api.md`).

## Out of scope (deferred)

- Token persistence beyond `sessionStorage`.
- CSV templates / sample downloads from the UI.
- Streaming / chunked uploads. With a 1 MB / 1000-row cap, a buffered read is
  fine.
- Update-on-conflict (upsert). Today duplicates are skipped, never merged.
- Audit log of imports.
