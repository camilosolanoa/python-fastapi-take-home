import csv
import io
import json
from pathlib import Path

import pytest
from psycopg import Connection
from psycopg.rows import DictRow

from app.records import CSV_COLUMNS
from scripts.load_data import load_data

BASE = [
    "1",
    "40",
    "Male",
    "Germany",
    "3.5",
    "328.1",
    "7.5",
    "Good",
    "24.9",
    "78",
    "Low",
    "14.5",
    "None",
    "Other",
    "0",
    "1",
]


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(rows)


def test_rejections_duplicates_conflicts_and_rerun(
    conn: Connection[DictRow], tmp_path: Path
) -> None:
    path = tmp_path / "sample.csv"
    repaired = BASE.copy()
    repaired[2] = " male "
    rows = [
        repaired,
        BASE,
        ["1", "35", *BASE[2:]],
        ["2", "oops", *BASE[2:]],
        ["2", "30", *BASE[2:]],
        ["short"],
        ["3", *BASE[1:]],
        ["3", *BASE[1:]],
        ["3", "50", *BASE[2:]],
        ["4", *BASE[1:14], "2", "0"],
    ]
    write_csv(path, rows)
    report = io.StringIO()
    result = load_data(path, conn, report, batch_size=2)
    assert (
        result.read,
        result.loaded,
        result.fixed,
        result.rejected,
        result.duplicates,
        result.conflicts,
    ) == (10, 3, 1, 3, 2, 2)
    issues = [json.loads(line) for line in report.getvalue().splitlines()]
    assert {(issue["line"], issue["kind"]) for issue in issues} == {
        (3, "duplicate"),
        (4, "conflict"),
        (5, "rejected"),
        (7, "rejected"),
        (9, "duplicate"),
        (10, "conflict"),
        (11, "rejected"),
    }
    assert all(issue["reason"] for issue in issues)
    assert conn.execute("SELECT id, age FROM coffee_records ORDER BY id").fetchall() == [
        {"id": 1, "age": 40},
        {"id": 2, "age": 30},
        {"id": 3, "age": 40},
    ]
    again = load_data(path, conn, io.StringIO(), batch_size=3)
    assert (again.loaded, again.duplicates, again.conflicts, again.rejected) == (0, 5, 2, 3)
    assert conn.execute("SELECT count(*) AS count FROM coffee_records").fetchone() == {"count": 3}


def test_reports_physical_line_after_multiline_field(
    conn: Connection[DictRow],
    tmp_path: Path,
) -> None:
    path = tmp_path / "multiline.csv"
    row = BASE.copy()
    row[3] = "South\nKorea"
    write_csv(path, [row, ["2", "bad", *BASE[2:]], ["3", *BASE[1:]]])
    report = io.StringIO()
    result = load_data(path, conn, report)
    assert (result.loaded, result.rejected) == (2, 1)
    assert json.loads(report.getvalue())["line"] == 4


def test_bad_header_fails_without_writes(conn: Connection[DictRow], tmp_path: Path) -> None:
    path = tmp_path / "wrong.csv"
    path.write_text("ID,Unexpected\n1,value\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        load_data(path, conn, io.StringIO())
    assert conn.execute("SELECT count(*) AS count FROM coffee_records").fetchone() == {"count": 0}


def test_blank_line_is_accounted_for(conn: Connection[DictRow], tmp_path: Path) -> None:
    path = tmp_path / "blank.csv"
    write_csv(path, [BASE, [], ["2", *BASE[1:]]])
    report = io.StringIO()
    result = load_data(path, conn, report)
    assert (result.read, result.loaded, result.rejected) == (3, 2, 1)
    assert json.loads(report.getvalue())["line"] == 3
