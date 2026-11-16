# Interview walkthrough

Use this as a rehearsal guide. Aim for a 5–7 minute demo, then leave time for questions.
Detailed assumptions and numeric limits are in [NOTES.md](NOTES.md).

## Before the call

- Start Docker, then `docker compose up -d --wait db`.
- Start the API: `uv run fastapi dev app/main.py` (only if it is not already running).
- Open http://localhost:8000/docs, the source files and the first-import report.
- Have the data loaded beforehand. Do not reset the database during the demo.

## Opening — 20 seconds

“This application imports a messy coffee-health CSV into PostgreSQL and exposes it through
FastAPI. I focused on validating data, making imports safe to repeat, and keeping memory
and API responses bounded.”

`CSV -> clean and validate -> PostgreSQL -> filtered, paginated API`

## Demo — 2 minutes

1. In `/docs`, run `GET /health`: the API can reach PostgreSQL.
2. Run `GET /records` with `country=Germany`, `min_age=30`, `max_age=50`, `limit=2`.
3. Copy `next_after_id` into `after_id`, keeping the filters. Show the next records.
4. Set `min_age=50`, `max_age=30`: show the clear 422 validation error.
5. Open [the first-import report](data/load_report.first.jsonl): show one rejection
   and one conflicting ID, including their source line numbers.
6. If useful, rerun `uv run python -m scripts.load_data data/coffee_health_raw.csv`.
   It should report zero new records against the already-loaded database.

## Code walkthrough — 3 minutes

### 1. Cleaning: `app/records.py`

“I trim spaces, standardize category capitalization and recognize explicit boolean values.
Pydantic then validates types, required fields and documented ranges. I repair formatting,
but do not guess missing or ambiguous values. For example, `male` becomes `Male`, while
`4O` is rejected rather than guessed to be `40`.”

Show `normalize_record` and the `Record` model. `Health_Issues=None` is a valid category.

### 2. Loading: `scripts/load_data.py`

“The reader processes one CSV record at a time. Invalid records are reported and skipped.
Valid records accumulate in batches of at most 1,000, which are written in a transaction.
The final partial batch is also saved.”

Show `load_data`, then `insert_batch`:

- `executemany` sends parameterized inserts using Psycopg's pipeline.
- `ON CONFLICT (id) DO NOTHING` prevents overwriting existing records.
- `RETURNING id` distinguishes inserted rows from skipped rows.
- Skipped rows are compared with saved values: identical means duplicate; different means conflict.
- Counters for inserted/skipped records are updated after the batch commits.

### 3. Storage: `db/init/001_records.sql`

“One table is enough for this dataset. The source ID is the primary key. PostgreSQL
constraints protect the stored data, and numeric columns preserve decimal precision.
The additional `(country, id)` index supports country filtering with ID pagination.”

### 4. API: `app/main.py`, then `app/db.py`

“Pydantic validates query parameters. The endpoint combines filters with AND and passes
values separately from SQL. It borrows a connection from the pool, fetches at most
`limit + 1` records, and returns a validated response plus the next cursor.”

The extra row tells us whether another page exists; it is not included in the response.
The pool is created once at startup and closed at shutdown, with at most 10 connections
per application process.

## Results — 20 seconds

“The import read 10,015 rows, including three blank lines. It saved 9,975 records,
rejected 28 rows, skipped eight duplicates and reported four conflicts. Fifty-six valid
rows had formatting repairs; that count overlaps with the other outcomes.
Running it again adds zero records. All 53 tests and the lint/type checks pass.”

## Likely questions — short answers

| Question | Answer |
| --- | --- |
| Why first valid record wins? | There is no trustworthy update timestamp or source priority. Keeping the first valid record is predictable and avoids silently replacing data. Existing database records win on reruns. |
| What makes reruns safe? | The primary key plus `ON CONFLICT DO NOTHING`. Deduplication happens in PostgreSQL, including across batches and runs. |
| What if two imports run together? | The unique key prevents duplicate IDs. The successful insert wins; concurrent order is not guaranteed to match either file's order. |
| What happens if the loader crashes? | The current transaction rolls back; earlier committed batches remain. A rerun skips those records. The report file is separate from the database transaction. |
| Why not one transaction for everything? | Smaller transactions bound rollback work and lock duration. The trade-off is that a failed import can leave partial, committed progress. |
| Why batches of 1,000? | A modest starting point that bounds memory and reduces transaction overhead. It is configurable in the loading function, not a benchmark-proven optimum. |
| Why not pandas? | The standard CSV reader is enough and naturally streams records. No extra dependency or whole-file dataframe is needed. |
| Why Psycopg instead of an ORM? | It is already in the starter, and the few SQL operations are straightforward. Direct SQL makes inserts, constraints and pagination easy to inspect. |
| Why Decimal / numeric? | To preserve source decimal values without binary floating-point rounding. The API returns decimal strings to retain that precision. |
| Why validate in Python and PostgreSQL? | Python provides useful row-level errors before insertion; database constraints protect integrity if another writer bypasses the loader. |
| How were numeric limits chosen? | They are explicit, broad ingestion assumptions, not clinical recommendations. I would confirm them with the data owner for a real system. |
| Why cursor pagination? | It resumes after an indexed ID instead of discarding an increasingly large OFFSET. It gives up arbitrary page-number jumps and exact totals. |
| Is cursor pagination always fast? | No. Selective filters can still scan many candidates. Indexes and actual query plans matter. |
| Is pagination a snapshot? | No. Concurrent imports can add records ahead of or behind the cursor. Repeatable traversal needs a stable dataset or a snapshot strategy. |
| Why not index every filter? | Indexes cost storage and slow writes. Start with the primary key and country/ID index, then measure before adding more. |
| Can it handle a file larger than RAM? | It streams the file and keeps only a bounded batch and its results. It does not retain every row or seen ID in Python. |
| What about tens of millions of rows? | Benchmark first. A likely improvement is COPY into a staging table followed by a set-based merge. The current pipeline is simple, but peak throughput is not proven. |
| How do concurrent API requests use connections? | Each request borrows and returns a pooled connection. The limit is per process, so adding workers multiplies the database connection budget. |
| How is SQL injection prevented? | Client values are bound parameters. Interpolated column names and operators come only from fixed application definitions. |
| What do the tests prove? | Cleaning rules without a database; real PostgreSQL imports and reruns; conflicts, reporting, filters, pagination and invalid query handling. They do not prove large-scale performance. |
| How did you use AI? | AI assisted implementation, tests and documentation. The submission records that use. I need to be able to explain and defend every decision and limitation. |

## If asked for a small change

“First I would clarify the expected behavior, add a focused test, make the smallest
change, and run the relevant checks.”

For a new filter: add its typed query parameter, add a parameterized condition, then test
matching/nonmatching records and invalid values. For a changed ingestion limit: update
the model, database constraint, boundary tests and documented assumption together.

Useful commands: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
and `uv run mypy`. On macOS/Linux, `make test` and `make lint` run these checks.
