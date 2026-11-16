import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from psycopg import Connection
from psycopg.rows import DictRow

from scripts.load_data import load_data
from tests.test_loader import BASE, write_csv


@pytest.mark.parametrize(
    "query",
    [
        "min_age=50&max_age=30",
        "min_coffee=4&max_coffee=1",
        "min_bmi=30&max_bmi=20",
        "min_coffee=NaN",
        "max_bmi=inf",
        "gender=Unknown",
        "stress_level=extreme",
        "min_age=17",
        "limit=0",
        "limit=201",
        "after_id=-1",
        "country=%20%20",
    ],
)
def test_invalid_query_returns_422(client: TestClient, query: str) -> None:
    response = client.get(f"/records?{query}")
    assert response.status_code == 422
    assert response.json()["detail"]


def test_filters_and_cursor_pages(
    client: TestClient,
    conn: Connection[DictRow],
    tmp_path: Path,
) -> None:
    path = tmp_path / "api.csv"
    rows = []
    for identifier, age, country, gender, stress in [
        (1, 25, "Germany", "Female", "Low"),
        (3, 35, "Germany", "Male", "High"),
        (5, 45, "France", "Male", "High"),
        (8, 55, "Germany", "Male", "High"),
    ]:
        row = BASE.copy()
        row[0:4] = [str(identifier), str(age), gender, country]
        row[10] = stress
        rows.append(row)
    write_csv(path, rows)
    load_data(path, conn, io.StringIO())

    first = client.get("/records?limit=2").json()
    assert [item["id"] for item in first["items"]] == [1, 3]
    assert first["next_after_id"] == 3
    second = client.get("/records?limit=2&after_id=3").json()
    assert [item["id"] for item in second["items"]] == [5, 8]
    assert second["next_after_id"] is None
    assert client.get("/records?after_id=8").json() == {"items": [], "next_after_id": None}

    filtered = client.get(
        "/records",
        params={
            "country": " germany ",
            "gender": "Male",
            "stress_level": "High",
            "sleep_quality": "Good",
            "min_age": 35,
            "max_age": 45,
            "min_coffee": "3.5",
            "max_coffee": "3.5",
            "min_bmi": "24.9",
            "max_bmi": "24.9",
        },
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [3]
    assert filtered.json()["items"][0]["coffee_intake"] == "3.5"
    assert filtered.json()["items"][0]["smoking"] is False
    assert client.get("/records", params={"country": "Germany' OR 1=1 --"}).json()["items"] == []
