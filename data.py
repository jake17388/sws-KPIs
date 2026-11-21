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
}
REQUIRED = ["Date", "Crew member", "Job number", "Total Estimated Job Hours",
            "Total Clocked Hours (Day)"]
FLAG_COLS = ["on_schedule", "fleetio_am", "fleetio_pm", "late_departure",
             "job_delay", "repair", "remake", "go_back"]


def read_source(file=None) -> pd.DataFrame:
    """Read the sample CSV, an uploaded CSV, or the Install Log sheet of an uploaded workbook."""
    if file is None:
        return pd.read_csv(SAMPLE_PATH)
    if file.name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(file, sheet_name="Install Log")
    return pd.read_csv(file)


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Standardize columns and compute estimated and actual hours per assignment."""
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    df = raw[[c for c in COLUMNS if c in raw.columns]].rename(columns=COLUMNS)
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
            vals = df[col].replace({"True": 1, "False": 0, "TRUE": 1, "FALSE": 0})
            df[col] = pd.to_numeric(vals, errors="coerce").fillna(0).astype(bool)
        else:
            df[col] = False
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
        df["day_pct"] = pd.to_numeric(df["day_pct"], errors="coerce").fillna(default_pct)
    else:
        df["day_pct"] = default_pct

    df["key"] = (df["crew"] + "|" + df["date"].dt.strftime("%Y-%m-%d") + "|"
                 + df["job_number"])
    return df.sort_values(["date", "crew", "job_number"]).reset_index(drop=True)


def apply_edits(df: pd.DataFrame, overrides: dict, est_overrides: dict,
                flag_overrides: dict | None = None) -> pd.DataFrame:
    """Apply Day % splits, edited estimates and edited checkboxes, then compute actual hours."""
    out = df.copy()
    for (key, col), value in (flag_overrides or {}).items():
        out.loc[out["key"] == key, col] = bool(value)
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
