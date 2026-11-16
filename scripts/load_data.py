"""Stream, validate and load a CSV: uv run python -m scripts.load_data <csv_path>."""

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

import psycopg
from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from pydantic import ValidationError

from app.config import settings
from app.records import CSV_COLUMNS, Record, normalize_record

COLUMNS = tuple(column.lower() for column in CSV_COLUMNS)
INSERT = (
    f"INSERT INTO coffee_records ({', '.join(COLUMNS)}) "
    f"VALUES ({', '.join(f'%({column})s' for column in COLUMNS)}) "
    "ON CONFLICT (id) DO NOTHING RETURNING id"
)


@dataclass
class Summary:
    read: int = 0
    loaded: int = 0
    fixed: int = 0
    rejected: int = 0
    duplicates: int = 0
    conflicts: int = 0


def report_row(report: TextIO, line: int, kind: str, reason: str) -> None:
    report.write(json.dumps({"line": line, "kind": kind, "reason": reason}) + "\n")


def insert_batch(
    conn: Connection[DictRow],
    batch: list[tuple[int, Record]],
    report: TextIO,
    summary: Summary,
) -> None:
    if not batch:
        return
    skipped: list[tuple[int, Record]] = []
    with conn.transaction():
        with conn.cursor() as cursor:
            # Psycopg pipelines executemany: bounded memory, no round trip per row.
            cursor.executemany(INSERT, [record.model_dump() for _, record in batch], returning=True)
            for line, record in batch:
                if cursor.fetchone() is None:
                    skipped.append((line, record))
                cursor.nextset()
        saved = (
            {
                row["id"]: Record.model_validate(row)
                for row in conn.execute(
                    "SELECT * FROM coffee_records WHERE id = ANY(%s)",
                    ([record.id for _, record in skipped],),
                ).fetchall()
            }
            if skipped
            else {}
        )
    # Count/report only after this batch commits successfully.
    summary.loaded += len(batch) - len(skipped)
    for line, record in skipped:
        if record == saved[record.id]:
            summary.duplicates += 1
            report_row(
                report, line, "duplicate", f"ID {record.id}: identical record already stored"
            )
        else:
            summary.conflicts += 1
            report_row(
                report, line, "conflict", f"ID {record.id}: different values; kept stored record"
            )


def load_data(
    path: Path,
    conn: Connection[DictRow],
    report: TextIO,
    batch_size: int = 1000,
) -> Summary:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if not conn.autocommit:
        raise ValueError("Use an autocommit connection so each batch commits independently")
    summary = Summary()
    batch: list[tuple[int, Record]] = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file, strict=True)
        if next(reader, None) != list(CSV_COLUMNS):
            raise ValueError("CSV header must match the documented 16 columns in order")
        while True:
            line = reader.line_num + 1
            try:
                cells = next(reader)
            except StopIteration:
                break
            except csv.Error as error:
                summary.read += 1
                summary.rejected += 1
                report_row(report, line, "rejected", f"CSV syntax: {error}")
                continue
            summary.read += 1
            try:
                if len(cells) != len(CSV_COLUMNS):
                    raise ValueError(f"Expected 16 columns, got {len(cells)}")
                record, fixed = normalize_record(dict(zip(CSV_COLUMNS, cells, strict=True)))
            except ValueError as error:
                summary.rejected += 1
                reason = str(error)
                if isinstance(error, ValidationError):
                    reason = "; ".join(
                        f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
                        for item in error.errors(include_url=False, include_context=False)
                    )
                report_row(report, line, "rejected", reason)
                continue
            summary.fixed += int(fixed)
            batch.append((line, record))
            if len(batch) == batch_size:
                insert_batch(conn, batch, report, summary)
                batch.clear()
        insert_batch(conn, batch, report, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--report", type=Path, default=Path("load_report.jsonl"))
    args = parser.parse_args()
    if args.csv_path.resolve() == args.report.resolve():
        parser.error("Report path must differ from the input CSV")
    with (
        psycopg.connect(settings.database_url, autocommit=True, row_factory=dict_row) as conn,
        args.report.open("w", encoding="utf-8") as report,
    ):
        result = load_data(args.csv_path, conn, report)
    print(json.dumps(asdict(result)))


if __name__ == "__main__":
    main()
