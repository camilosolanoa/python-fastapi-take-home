"""Shared record types and conservative CSV normalization."""

from decimal import Decimal
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

Gender = Literal["Male", "Female", "Other"]
SleepQuality = Literal["Poor", "Fair", "Good", "Excellent"]
StressLevel = Literal["Low", "Medium", "High"]
HealthIssues = Literal["None", "Mild", "Moderate", "Severe"]
Occupation = Literal["Office", "Healthcare", "Service", "Student", "Other"]

CSV_COLUMNS = (
    "ID",
    "Age",
    "Gender",
    "Country",
    "Coffee_Intake",
    "Caffeine_mg",
    "Sleep_Hours",
    "Sleep_Quality",
    "BMI",
    "Heart_Rate",
    "Stress_Level",
    "Physical_Activity_Hours",
    "Health_Issues",
    "Occupation",
    "Smoking",
    "Alcohol_Consumption",
)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    id: int = Field(ge=1, le=9223372036854775807)
    age: int = Field(ge=18, le=120)
    gender: Gender
    country: str = Field(min_length=1, max_length=100)
    coffee_intake: Decimal = Field(ge=0, le=30)
    caffeine_mg: Decimal = Field(ge=0, le=5000)
    sleep_hours: Decimal = Field(ge=0, le=24)
    sleep_quality: SleepQuality
    bmi: Decimal = Field(ge=10, le=100)
    heart_rate: int = Field(ge=30, le=250)
    stress_level: StressLevel
    physical_activity_hours: Decimal = Field(ge=0, le=168)
    health_issues: HealthIssues
    occupation: Occupation
    smoking: bool
    alcohol_consumption: bool


CATEGORIES: dict[str, tuple[str, ...]] = {
    "gender": get_args(Gender),
    "sleep_quality": get_args(SleepQuality),
    "stress_level": get_args(StressLevel),
    "health_issues": get_args(HealthIssues),
    "occupation": get_args(Occupation),
}
BOOLEANS = {
    "0": "0",
    "1": "1",
    "no": "0",
    "yes": "1",
    "n": "0",
    "y": "1",
    "false": "0",
    "true": "1",
}


def normalize_country(value: str) -> str:
    if "\x00" in value:
        raise ValueError("country: NUL characters are not valid text")
    value = " ".join(value.split())
    return value.upper() if value.upper() in {"USA", "UK"} else value.title()


def normalize_record(raw: dict[str, str]) -> tuple[Record, bool]:
    """Return a validated record and whether its input formatting was repaired."""
    values = {key.lower(): value.strip() for key, value in raw.items()}
    for field, choices in CATEGORIES.items():
        if field in values:
            canonical = {choice.casefold(): choice for choice in choices}
            values[field] = canonical.get(values[field].casefold(), values[field])
    if "country" in values:
        values["country"] = normalize_country(values["country"])
    for field in ("smoking", "alcohol_consumption"):
        if field in values:
            value = BOOLEANS.get(values[field].casefold())
            if value is None:
                raise ValueError(f"{field}: expected 0/1, yes/no, true/false or y/n")
            values[field] = value
    record = Record.model_validate(values)
    fixed = any(values[key.lower()] != value for key, value in raw.items())
    return record, fixed
