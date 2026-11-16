from decimal import Decimal

import pytest

from app.records import normalize_record


@pytest.fixture
def raw_record() -> dict[str, str]:
    return {
        "ID": "1",
        "Age": "40",
        "Gender": "Male",
        "Country": "Germany",
        "Coffee_Intake": "3.5",
        "Caffeine_mg": "328.1",
        "Sleep_Hours": "7.5",
        "Sleep_Quality": "Good",
        "BMI": "24.9",
        "Heart_Rate": "78",
        "Stress_Level": "Low",
        "Physical_Activity_Hours": "14.5",
        "Health_Issues": "None",
        "Occupation": "Other",
        "Smoking": "0",
        "Alcohol_Consumption": "1",
    }


def test_valid_record_preserves_values(raw_record: dict[str, str]) -> None:
    record, fixed = normalize_record(raw_record)
    assert record.id == 1
    assert record.caffeine_mg == Decimal("328.1")
    assert record.health_issues == "None"  # A real category, not a missing value.
    assert record.smoking is False
    assert record.alcohol_consumption is True
    assert not fixed


def test_repairs_only_clear_formatting(raw_record: dict[str, str]) -> None:
    raw_record.update(
        Gender=" male ",
        Country="  south   KOREA ",
        Age=" 40 ",
        Smoking="NO",
        Alcohol_Consumption=" Y ",
        Sleep_Quality="GOOD",
    )
    record, fixed = normalize_record(raw_record)
    assert (record.gender, record.country, record.age) == ("Male", "South Korea", 40)
    assert (record.smoking, record.alcohol_consumption, record.sleep_quality) == (
        False,
        True,
        "Good",
    )
    assert fixed


@pytest.mark.parametrize("country,expected", [("usa", "USA"), (" uk ", "UK"), ("SWEDEN", "Sweden")])
def test_country_format(raw_record: dict[str, str], country: str, expected: str) -> None:
    raw_record["Country"] = country
    assert normalize_record(raw_record)[0].country == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("ID", "0"),
        ("ID", "9223372036854775808"),
        ("Age", "17"),
        ("Age", "121"),
        ("Age", "4O"),
        ("Age", "thirty"),
        ("Age", "40.5"),
        ("Age", ""),
        ("Gender", "?"),
        ("Country", "  "),
        ("Country", "Ger\x00many"),
        ("Coffee_Intake", "-1"),
        ("Coffee_Intake", "31"),
        ("Caffeine_mg", "5001"),
        ("Sleep_Hours", "25"),
        ("Sleep_Hours", "NaN"),
        ("BMI", "0"),
        ("BMI", "Infinity"),
        ("Heart_Rate", "350"),
        ("Heart_Rate", "0"),
        ("Physical_Activity_Hours", "169"),
        ("Sleep_Quality", "Amazing"),
        ("Stress_Level", "Unknown"),
        ("Health_Issues", ""),
        ("Occupation", "N/A"),
        ("Smoking", "2"),
        ("Smoking", "-1"),
        ("Alcohol_Consumption", "maybe"),
    ],
)
def test_rejects_invalid_values(raw_record: dict[str, str], field: str, value: str) -> None:
    raw_record[field] = value
    with pytest.raises(ValueError):
        normalize_record(raw_record)


def test_accepts_inclusive_limits(raw_record: dict[str, str]) -> None:
    raw_record.update(
        Age="120",
        Coffee_Intake="0",
        Caffeine_mg="0",
        Sleep_Hours="24",
        BMI="10",
        Heart_Rate="30",
        Physical_Activity_Hours="168",
    )
    record, _ = normalize_record(raw_record)
    assert record.age == 120
    assert record.sleep_hours == Decimal("24")
    assert record.physical_activity_hours == Decimal("168")


def test_decimal_precision_is_not_silently_rounded(raw_record: dict[str, str]) -> None:
    raw_record["Coffee_Intake"] = "3.12345"
    assert normalize_record(raw_record)[0].coffee_intake == Decimal("3.12345")
