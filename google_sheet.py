"""Read and update the Google Sheets Install Log worksheet."""
from __future__ import annotations

from io import StringIO
import os
import time

import pandas as pd
import requests

import data

SHEET_ID = "1pBYUoM3gxQoSjnrihwcKcTZHqO_BGXiWo3aZnzuat2A"
WORKSHEET_NAME = "Install Log"
WORKSHEET_GID = 1604393046
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"

EDITABLE_FIELDS = {
    "day_pct": lambda value: f"{float(value):g}%",
    "est_hours_input": lambda value: float(value),
    "on_schedule": bool,
    "fleetio_am": bool,
    "fleetio_pm": bool,
    "late_departure": bool,
    "job_delay": bool,
    "repair": bool,
    "remake": bool,
    "go_back": bool,
    "notes": str,
}


def public_csv_url() -> str:
    """Direct CSV export for the Install Log tab, bypassing the gviz query cache."""
    return (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export"
            f"?format=csv&gid={WORKSHEET_GID}&cache_bust={time.time_ns()}")


def read_install_log() -> pd.DataFrame:
    """Read only the public Install Log worksheet and retain source row numbers."""
    local_path = os.environ.get("INSTALL_LOG_CSV_PATH")
    if local_path:
        raw = pd.read_csv(local_path)
    else:
        response = requests.get(
            public_csv_url(), timeout=30,
            headers={"User-Agent": "Install-Crew-KPI-Dashboard/1.0",
                     "Cache-Control": "no-cache", "Pragma": "no-cache"})
        response.raise_for_status()
        raw = pd.read_csv(StringIO(response.text))
    raw[data.SOURCE_ROW] = range(2, len(raw) + 2)
    return raw


def percentage_source(raw: pd.DataFrame) -> tuple[str | None, str | None]:
    """Return the source header and column letter used for day percentages."""
    mapping = data.source_column_map(raw.columns)
    return mapping.get("day_pct"), data.source_column_letter(raw.columns, "day_pct")


def pending_count(day_pct: dict, estimates: dict, flags: dict, notes: dict) -> int:
    return len(day_pct) + len(estimates) + len(flags) + len(notes)


def build_updates(log: pd.DataFrame, headers: list[str], day_pct: dict, estimates: dict,
                  flags: dict, notes: dict) -> list[dict]:
    """Build gspread batch-update entries for the exact source rows and mapped headers."""
    if data.SOURCE_ROW not in log:
        raise ValueError("Google Sheet row numbers are unavailable; reload the Install Log.")
    mapped = data.source_column_map(headers)
    header_positions = {header: i + 1 for i, header in enumerate(headers)}
    rows = log.set_index("key")[data.SOURCE_ROW].astype(int).to_dict()
    changes = []
    changes.extend((key, "day_pct", value) for key, value in day_pct.items())
    changes.extend((key, "est_hours_input", value) for key, value in estimates.items())
    changes.extend((key, field, value) for (key, field), value in flags.items())
    changes.extend((key, "notes", value) for key, value in notes.items())

    missing = sorted({field for _, field, _ in changes if field not in mapped})
    if missing:
        readable = ", ".join(missing)
        raise ValueError(f"Install Log is missing writable column(s): {readable}")

    updates = []
    for key, field, value in changes:
        if key not in rows:
            raise ValueError(f"Could not find the source row for edited assignment {key!r}.")
        column = header_positions[mapped[field]]
        number = column
        letters = ""
        while number:
            number, remainder = divmod(number - 1, 26)
            letters = chr(65 + remainder) + letters
        updates.append({"range": f"{letters}{rows[key]}",
                        "values": [[EDITABLE_FIELDS[field](value)]]})
    return updates


def validate_source_rows(loaded_log: pd.DataFrame, current_log: pd.DataFrame,
                         edited_keys: set[str]) -> None:
    """Fail safely if sheet rows moved or changed after the dashboard loaded."""
    identity = ["date", "crew", "job_number"]
    loaded = loaded_log.set_index("key")
    current = current_log.set_index(data.SOURCE_ROW)
    for key in edited_keys:
        if key not in loaded.index:
            raise ValueError(f"Edited assignment {key!r} is no longer loaded.")
        old = loaded.loc[key]
        row_number = int(old[data.SOURCE_ROW])
        if row_number not in current.index:
            raise ValueError("Install Log rows changed. Refresh the Google Sheet and try again.")
        new = current.loc[row_number]
        if any(str(old[field]) != str(new[field]) for field in identity):
            raise ValueError("Install Log rows changed. Refresh the Google Sheet and try again.")


def save_edits(service_account_info: dict, log: pd.DataFrame, day_pct: dict,
               estimates: dict, flags: dict, notes: dict) -> int:
    """Write pending edits to Install Log using a read/write service account."""
    import gspread

    info = dict(service_account_info)
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    client = gspread.service_account_from_dict(info)
    worksheet = client.open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)
    headers = worksheet.row_values(1)
    current_raw = pd.DataFrame(worksheet.get_all_records())
    current_raw[data.SOURCE_ROW] = range(2, len(current_raw) + 2)
    current_log = data.clean(current_raw)
    edited_keys = (set(day_pct) | set(estimates) | set(notes)
                   | {key for key, _ in flags})
    validate_source_rows(log, current_log, edited_keys)
    updates = build_updates(log, headers, day_pct, estimates, flags, notes)
    if updates:
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
    return len(updates)
