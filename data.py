"""Loading and cleaning install log data."""
from pathlib import Path

import numpy as np
import pandas as pd

SAMPLE_PATH = Path(__file__).parent / "data" / "sample_install_log.csv"

# Source column name -> internal name
COLUMNS = {
    "Date": "date",
    "Crew member": "crew",
    "Job number": "job_number",
    "Job name": "job_name",
    "Truck": "truck",
    "Crew Size": "crew_size",
    "Total Estimated Job Hours": "est_job_hours",
    "Total Clocked Hours (Day)": "clocked_hours",
    "Est. Hours (Day)": "est_hours_input",
    "Day %": "day_pct",
    "Work Completed on Schedule": "on_schedule",
    "Fleetio AM": "fleetio_am",
    "Fleetio PM": "fleetio_pm",
    "Late Departure (After 6:30)": "late_departure",
    "Job Delay": "job_delay",
    "Repair": "repair",
    "Remake": "remake",
    "Go Back": "go_back",
    "Notes": "notes",
}
ALIASES = {
    "date": ["Date", "Install Date"],
    "crew": ["Crew member", "Crew Member", "Installer", "Employee"],
    "job_number": ["Job number", "Job Number", "Job #", "Job"],
    "job_name": ["Job name", "Job Name", "Project name", "Project Name"],
    "truck": ["Truck", "Vehicle"],
    "crew_size": ["Crew Size", "Crew size"],
    "est_job_hours": ["Total Estimated Job Hours", "Estimated Job Hours"],
    "clocked_hours": ["Total Clocked Hours (Day)", "Clocked Hours", "Total Clocked Hours"],
    "est_hours_input": ["Est. Hours (Day)", "Estimated Hours (Day)",
                        "Estimated Project Hours (Day)"],
    "day_pct": ["Day Allocation %", "Day %", "% of Day", "Percent of Day",
                "Percentage of Day", "Day Percentage"],
    "on_schedule": ["Work Completed on Schedule", "On Schedule"],
    "fleetio_am": ["Fleetio AM"],
    "fleetio_pm": ["Fleetio PM"],
    "late_departure": ["Late Departure (After 6:30)", "Late Departure"],
    "job_delay": ["Job Delay"],
    "repair": ["Repair"],
    "remake": ["Remake"],
    "go_back": ["Go Back", "Go back"],
    "notes": ["Notes", "Note", "Install Notes", "Comments"],
}
REQUIRED = ["Date", "Crew member", "Job number", "Total Estimated Job Hours",
            "Total Clocked Hours (Day)"]
REQUIRED_INTERNAL = ["date", "crew", "job_number", "est_job_hours", "clocked_hours"]
FLAG_COLS = ["on_schedule", "fleetio_am", "fleetio_pm", "late_departure",
             "job_delay", "repair", "remake", "go_back"]
SOURCE_ROW = "_sheet_row"


def _normalized_header(value) -> str:
    return " ".join(str(value).strip().casefold().split())


def source_column_map(columns) -> dict[str, str]:
    """Return internal field -> actual source header, accepting common header variants."""
    actual = {_normalized_header(column): column for column in columns if column != SOURCE_ROW}
    mapped = {}
    for internal, aliases in ALIASES.items():
        for alias in aliases:
            if _normalized_header(alias) in actual:
                mapped[internal] = actual[_normalized_header(alias)]
                break
    return mapped


def source_column_letter(columns, internal: str) -> str | None:
    """Return an A1-style column letter for a mapped field."""
    mapped = source_column_map(columns)
    if internal not in mapped:
        return None
    number = list(columns).index(mapped[internal]) + 1
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _percent_series(series: pd.Series) -> pd.Series:
    """Convert values such as 50%, 50, or numeric 0.5 to percentage points."""
    text = series.astype("string").str.strip()
    has_percent = text.str.endswith("%", na=False)
    values = pd.to_numeric(text.str.rstrip("%").str.replace(",", "", regex=False),
                           errors="coerce")
    fractional = ~has_percent & values.between(0, 1, inclusive="both")
    return values.where(~fractional, values * 100)


def _boolean_series(series: pd.Series) -> pd.Series:
    truthy = {"1", "true", "yes", "y", "x", "checked", "☑", "☒"}
    return series.map(lambda value: _normalized_header(value) in truthy
                      if not pd.isna(value) else False).astype(bool)


def read_source(file=None) -> pd.DataFrame:
    """Read the sample CSV, an uploaded CSV, or the Install Log sheet of an uploaded workbook."""
    if file is None:
        return pd.read_csv(SAMPLE_PATH)
    if file.name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(file, sheet_name="Install Log")
    return pd.read_csv(file)


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Standardize columns and compute estimated and actual hours per assignment."""
    source_columns = list(raw.columns)
    mapped = source_column_map(source_columns)
    missing = [internal for internal in REQUIRED_INTERNAL if internal not in mapped]
    if missing:
        labels = {value: key for key, value in COLUMNS.items()}
        raise ValueError(f"Missing required columns: {', '.join(labels.get(c, c) for c in missing)}")

    rename = {source: internal for internal, source in mapped.items()}
    selected = list(rename)
    if SOURCE_ROW in raw:
        selected.append(SOURCE_ROW)
    df = raw[selected].rename(columns=rename)
    df = df.dropna(subset=["date", "crew", "job_number"]).copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["crew"] = df["crew"].astype(str).str.strip()
    df["job_number"] = df["job_number"].astype(str).str.replace(r"\.0$", "", regex=True)
    if "job_name" not in df:
        df["job_name"] = df["job_number"]
    df["job_name"] = (df["job_name"].fillna(df["job_number"]).astype(str)
                      .str.replace(r"\.0$", "", regex=True))
    df["truck"] = df["truck"].fillna("Not logged") if "truck" in df else "Not logged"

    # Yes/no KPIs become True/False (blank = not checked)
    for col in FLAG_COLS:
        if col in df:
            df[col] = _boolean_series(df[col])
        else:
            df[col] = False
    if "notes" not in df:
        df["notes"] = ""
    else:
        df["notes"] = df["notes"].fillna("").astype(str)
    df["est_job_hours"] = pd.to_numeric(df["est_job_hours"], errors="coerce").fillna(0)
    df["clocked_hours"] = pd.to_numeric(df["clocked_hours"], errors="coerce")

    # Crew size: people on that job that day (recount if not supplied)
    counted = df.groupby(["job_number", "date"])["crew"].transform("nunique")
    df["crew_size"] = (pd.to_numeric(df["crew_size"], errors="coerce").fillna(counted)
                       if "crew_size" in df else counted)

    # Estimated hours per person per day: job estimate spread over its scheduled days and crew
    job_days = df.groupby("job_number")["date"].transform("nunique")
    est = df["est_job_hours"] / job_days / df["crew_size"].clip(lower=1)
    df["est_hours"] = est.where(df["est_job_hours"] > 0).round(2)
    # Keep per-row estimates edited earlier (from a re-uploaded export)
    if "est_hours_input" in df:
        saved = pd.to_numeric(df["est_hours_input"], errors="coerce")
        df["est_hours"] = saved.fillna(df["est_hours"])
        df = df.drop(columns="est_hours_input")

    # Worked = has clocked hours (future scheduled rows stay out of KPIs)
    df["worked"] = df["clocked_hours"].fillna(0) > 0
    df["jobs_that_day"] = df.groupby(["crew", "date"])["job_number"].transform("count")

    # Default split is even across jobs that day; keep any saved Day % from a re-upload
    default_pct = (100 / df["jobs_that_day"]).round(1)
    if "day_pct" in df:
        df["day_pct"] = _percent_series(df["day_pct"]).fillna(default_pct).clip(0, 100)
    else:
        df["day_pct"] = default_pct

    df["key"] = (df["crew"] + "|" + df["date"].dt.strftime("%Y-%m-%d") + "|"
                 + df["job_number"])
    if SOURCE_ROW in df:
        df["key"] += "|row-" + df[SOURCE_ROW].astype(int).astype(str)
    result = df.sort_values(["date", "crew", "job_number"]).reset_index(drop=True)
    result.attrs["source_columns"] = source_columns
    result.attrs["source_column_map"] = mapped
    return result


def apply_edits(df: pd.DataFrame, overrides: dict, est_overrides: dict,
                flag_overrides: dict | None = None,
                notes_overrides: dict | None = None) -> pd.DataFrame:
    """Apply Day % splits, edited estimates and edited checkboxes, then compute actual hours."""
    out = df.copy()
    for (key, col), value in (flag_overrides or {}).items():
        out.loc[out["key"] == key, col] = bool(value)
    for key, value in (notes_overrides or {}).items():
        out.loc[out["key"] == key, "notes"] = str(value)
    if overrides:
        out["day_pct"] = out["key"].map(overrides).fillna(out["day_pct"])
    out["est_edited"] = out["key"].isin(est_overrides)
    if est_overrides:
        edited = out["est_edited"]
        out.loc[edited, "est_hours"] = pd.to_numeric(
            out.loc[edited, "key"].map(est_overrides), errors="coerce")
    out["est_hours"] = out["est_hours"].where(out["est_hours"] > 0)  # 0 = no estimate
    out["actual_hours"] = (out["clocked_hours"] * out["day_pct"] / 100).round(2)
    return out


def export(df: pd.DataFrame) -> str:
    """CSV in the source column names, with Day % and edited estimates, so it can be re-uploaded."""
    back = {v: k for k, v in COLUMNS.items()}
    back["est_hours"] = "Est. Hours (Day)"
    cols = [c for c in back if c in df.columns]
    out = df[cols].rename(columns=back)
    out["Date"] = out["Date"].dt.date
    return out.to_csv(index=False)
