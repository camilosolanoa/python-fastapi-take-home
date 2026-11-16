# Implementation notes

## Design

`CSV -> Python validation -> PostgreSQL -> FastAPI -> /docs`

- `app/records.py`: typed record, validation and normalization (no database dependency).
- `scripts/load_data.py`: streaming CSV reader, batched inserts, import report.
- `db/init/001_records.sql`: one table, constraints and indexes.
- `app/main.py`: filters, parameterized queries and cursor pagination.
- `app/db.py`: the starter's connection pool, opened/closed with the application.

The starter notes table/endpoint were removed. No ORM, frontend, login or deployment
is needed for this exercise. Run the loader as a module (`python -m scripts.load_data`)
from the repository root so Python resolves `app` without modifying `sys.path`.

## Schema and cleaning

The source ID is the primary key (`bigint`). Integers, booleans and exact PostgreSQL
`numeric` values represent the source types. Decimal columns have no fixed scale:
accepted precision is preserved, not silently rounded. Required fields are `NOT NULL`;
database checks also enforce categories and these inclusive ingestion limits:

| Field | Accepted range |
| --- | --- |
| ID | 1 to 9,223,372,036,854,775,807 |
| Age | 18–120 years |
| Coffee intake | 0–30 cups/day |
| Caffeine | 0–5,000 mg/day |
| Sleep | 0–24 hours/night |
| BMI | 10–100 |
| Resting heart rate | 30–250 beats/minute |
| Physical activity | 0–168 hours/week |

These are broad data-quality assumptions, not healthy recommended ranges. No caffeine
per-cup ratio is enforced: servings and other caffeine sources can differ.

Read UTF-8 with optional BOM and require the documented header/column order. Trim outer
whitespace, match category casing, collapse country whitespace and title-case names
(preserving USA/UK). Country is nonempty text of up to 100 characters, not an authoritative
geographic lookup. Reject NUL text. Accept 0/1, true/false, yes/no and y/n for booleans.
`Health_Issues=None` is a valid category, not missing data.

Reject missing values, unknown categories, fractional integers, nonfinite/out-of-range
numbers and wrong column counts. Do not guess that `4O` means `40`, impute missing values,
or discard extra columns. Blank lines are counted and rejected. CSV syntax errors are
reported at the start of the affected record; broken quoting can consume several physical
lines, so recovery cannot reconstruct lost record boundaries.

## Duplicates and results

First valid record wins, in file order. An invalid row does not reserve its ID.
On later runs, existing database records win. Identical normalized rows are duplicates;
different values for an existing ID are conflicts, reported without overwriting data.
This also works across batch boundaries. With simultaneous loaders, the database's
unique key resolves insert races; whichever insert succeeds first wins.

Verified on the supplied, unchanged CSV against an empty database:

| Outcome | Count |
| --- | ---: |
| Rows read (excluding header, including 3 blank lines) | 10,015 |
| Newly loaded | 9,975 |
| Rejected | 28 |
| Identical duplicates | 8 |
| Conflicting duplicates | 4 |
| Valid rows with formatting repairs | 56 |

`read = loaded + rejected + duplicates + conflicts`. **Fixed is an overlapping count**
of valid rows whose formatting changed, including any skipped duplicates/conflicts.
The database count is 9,975. The 28 rejections are: age 7, gender 3, sleep 4, BMI 3,
heart rate 3, smoking 2, wrong column counts 3, and blank lines 3. The source has 10,000
distinct IDs; 25 have no valid record, independently reconciling the final count.

[First-import report](data/load_report.first.jsonl) records all 40 excluded rows with
physical starting line numbers and reasons. Reports may be out of line order because
duplicates are classified when a batch is written. Default `load_report.jsonl` is
overwritten on each run; use `--report another-path.jsonl` to preserve another report.

A second run loaded **0**, with **9,983 duplicates**, **4 conflicts** and **28 rejections**.
No stored values changed. A local first import took approximately 2.4 seconds including
process startup; this is an observation, not a prediction for larger or remote systems.

## API

`GET /records` supports country, gender, sleep quality and stress level equality, plus
inclusive `min_age/max_age`, `min_coffee/max_coffee` and `min_bmi/max_bmi` ranges.
Filters combine with AND. Country uses the same normalization as imports; other categories
use the documented canonical values. Invalid values or reversed ranges return 422.
All client values are SQL parameters; only fixed application column names/operators
are interpolated. Pydantic validates responses; decimals serialize as exact JSON strings.

Pagination uses `id > after_id ORDER BY id LIMIT limit+1`: default 50, maximum 200.
Return `items` and `next_after_id` (null at the end). Keep the filters and limit unchanged
when following the cursor. There is no full-table count or arbitrary page-number jump.
Pagination is not a snapshot: concurrent imports can add higher IDs or insert lower IDs
behind an already-consumed cursor. Use a stable dataset for a repeatable full traversal.

## Scale and verification

- The loader holds at most 1,000 valid records plus bounded batch results; it does not
  accumulate the CSV or all seen IDs. Reports stream to disk. Psycopg's pipelined
  `executemany` avoids a network round trip for every insert.
- Each batch is a transaction. An unexpected database/file failure stops the command;
  prior batches remain committed and a rerun safely resumes by skipping existing IDs.
  This favors bounded transactions over whole-file atomicity. The report file is not
  transactionally coupled to PostgreSQL; rerun after a crash to produce a complete report.
- At tens of millions of rows, benchmark Python parsing, network and write throughput.
  `COPY` into a staging table followed by a set-based merge is a possible next optimization;
  it is more complex than the current bounded, pipelined inserts.
- The primary key supports unfiltered cursor pages. `(country, id)` supports country
  equality with the cursor/order. Every index adds storage and write cost; low-cardinality
  fields do not automatically merit individual indexes. Add range/composite indexes only
  after examining real query plans and selectivity.
- Cursor pagination avoids scanning an increasing OFFSET. Selective filters can still
  require scanning many candidates. On this 10k-row dataset, `EXPLAIN ANALYZE` chose the
  primary-key index even for a country-filtered late page; large-data performance needs
  measurement rather than extrapolation from this small table.
- The existing pool has 1–10 connections **per process**. Synchronous endpoints run in
  FastAPI's thread pool and return connections after requests. More workers multiply the
  connection budget; tune worker/pool sizes and queue timeouts to the database capacity.

`make test` passes 53 tests: normalization without PostgreSQL, real-database imports,
reruns/conflicts, malformed and multiline rows, filtering, pagination and 422 responses.
Integration tests create/drop their own schemas, preserving application data.
`make lint` passes Ruff, formatting and strict mypy. GitHub Actions runs the same checks.

AI assisted implementation, testing and documentation. The rules and trade-offs above
are explicit so the solution can be reviewed and explained without the assistant.
