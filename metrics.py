"""KPI calculations. All functions expect worked rows from data.apply_splits."""
import numpy as np
import pandas as pd

KPI_LABELS = {
    "on_schedule_pct": "On-Schedule %",
    "fleetio_pct": "Fleetio Inspection %",
    "efficiency_pct": "Hours Efficiency %",
    "late_departures": "Late Departures",
    "callbacks": "Go Backs / Remakes / Repairs",
    "job_delays": "Job Delays",
}


def _safe_div(a, b):
    return np.where(b > 0, a / np.where(b > 0, b, 1), np.nan)


def summarize(df: pd.DataFrame, by=None) -> pd.DataFrame:
    """KPI summary per group (by='crew', or a list like ['week', 'crew']), or one team row."""
    keys = [by] if isinstance(by, str) else list(by or [])
    work = df if keys else df.assign(_all="Team")
    keys = keys or ["_all"]

    # Day-level KPIs: count each crew member's day once, even with several jobs
    day_keys = keys + [k for k in ["crew", "date"] if k not in keys]
    daily = (work.groupby(day_keys, as_index=False)
             .agg(clocked=("clocked_hours", "max"), am=("fleetio_am", "max"),
                  pm=("fleetio_pm", "max"), late=("late_departure", "max")))
    daily["fleetio_done"] = (daily["am"].fillna(0).astype(int)
                             + daily["pm"].fillna(0).astype(int))
    daily["fleetio_logged"] = np.where(daily["am"].notna() | daily["pm"].notna(), 2, 0)
    day = daily.groupby(keys).agg(
        days=("date", "count"),
        clocked_hours=("clocked", "sum"),
        fleetio_done=("fleetio_done", "sum"),
        fleetio_logged=("fleetio_logged", "sum"),
        late_departures=("late", "sum"),
    )

    # Assignment-level KPIs
    with_est = work["est_hours"].notna()
    job = work.assign(
        est_used=work["est_hours"].where(with_est),
        act_used=work["actual_hours"].where(with_est),
        callback=work[["go_back", "remake", "repair"]].astype(float).sum(axis=1, min_count=1),
    ).groupby(keys).agg(
        assignments=("job_number", "count"),
        jobs=("job_number", "nunique"),
        on_schedule_pct=("on_schedule", "mean"),
        est_hours=("est_used", "sum"),
        actual_hours=("act_used", "sum"),
        actual_hours_all=("actual_hours", "sum"),
        callbacks=("callback", "sum"),
        job_delays=("job_delay", "sum"),
    )

    out = day.join(job)
    out["on_schedule_pct"] = out["on_schedule_pct"] * 100
    out["fleetio_pct"] = _safe_div(out["fleetio_done"], out["fleetio_logged"]) * 100
    out["efficiency_pct"] = _safe_div(out["est_hours"], out["actual_hours"]) * 100
    out = out.drop(columns=["fleetio_done", "fleetio_logged"])
    for col in ["late_departures", "callbacks", "job_delays"]:
        out[col] = out[col].astype(int)
    if isinstance(by, str):
        out.index.name = by
    return out.round(1)


def goal_status(value, goal, higher_is_better=True):
    """Return a small status label for a KPI against its goal."""
    if pd.isna(value):
        return "No data"
    good = value >= goal if higher_is_better else value <= goal
    return "On target" if good else "Below goal" if higher_is_better else "Over limit"
