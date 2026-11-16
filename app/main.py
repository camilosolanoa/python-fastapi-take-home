from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Self

from fastapi import Depends, FastAPI, Query
from psycopg import Connection
from psycopg.rows import DictRow
from pydantic import BaseModel, Field, field_validator, model_validator

from app.db import create_pool, get_conn
from app.records import Gender, Record, SleepQuality, StressLevel, normalize_country


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pool = create_pool()
    try:
        yield
    finally:
        app.state.pool.close()


app = FastAPI(title="Coffee Health API", lifespan=lifespan)

Conn = Annotated[Connection[DictRow], Depends(get_conn)]


class Health(BaseModel):
    status: str
    database: str


class Filters(BaseModel):
    country: str | None = Field(default=None, min_length=1, max_length=100)
    gender: Gender | None = None
    sleep_quality: SleepQuality | None = None
    stress_level: StressLevel | None = None
    min_age: int | None = Field(default=None, ge=18, le=120)
    max_age: int | None = Field(default=None, ge=18, le=120)
    min_coffee: Decimal | None = Field(default=None, ge=0, le=30, allow_inf_nan=False)
    max_coffee: Decimal | None = Field(default=None, ge=0, le=30, allow_inf_nan=False)
    min_bmi: Decimal | None = Field(default=None, ge=10, le=100, allow_inf_nan=False)
    max_bmi: Decimal | None = Field(default=None, ge=10, le=100, allow_inf_nan=False)
    after_id: int = Field(default=0, ge=0, le=9223372036854775807)
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("country")
    @classmethod
    def clean_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = normalize_country(value)
        if not value:
            raise ValueError("country must not be blank")
        return value

    @model_validator(mode="after")
    def ordered_ranges(self) -> Self:
        for name in ("age", "coffee", "bmi"):
            lower, upper = getattr(self, f"min_{name}"), getattr(self, f"max_{name}")
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"min_{name} must be less than or equal to max_{name}")
        return self


class RecordPage(BaseModel):
    items: list[Record]
    next_after_id: int | None


@app.get("/health")
def health(conn: Conn) -> Health:
    conn.execute("select 1")
    return Health(status="ok", database="ok")


@app.get("/records")
def list_records(conn: Conn, filters: Annotated[Filters, Query()]) -> RecordPage:
    """Filters combine with AND; ranges are inclusive. Keep filters unchanged between pages."""
    clauses = ["id > %s"]
    params: list[object] = [filters.after_id]
    for column in ("country", "gender", "sleep_quality", "stress_level"):
        value = getattr(filters, column)
        if value is not None:
            clauses.append(f"{column} = %s")
            params.append(value)
    for name, column in (("age", "age"), ("coffee", "coffee_intake"), ("bmi", "bmi")):
        for prefix, operator in (("min", ">="), ("max", "<=")):
            value = getattr(filters, f"{prefix}_{name}")
            if value is not None:
                clauses.append(f"{column} {operator} %s")
                params.append(value)
    params.append(filters.limit + 1)
    # SQL fragments above are constants; all client values are bound parameters.
    rows = conn.execute(
        "SELECT * FROM coffee_records WHERE " + " AND ".join(clauses) + " ORDER BY id LIMIT %s",
        params,
    ).fetchall()
    items = [Record.model_validate(row) for row in rows[: filters.limit]]
    return RecordPage(
        items=items,
        next_after_id=items[-1].id if len(rows) > filters.limit else None,
    )
