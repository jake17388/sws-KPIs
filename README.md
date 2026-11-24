# Install Crew KPI Dashboard

A Streamlit dashboard for tracking sign install crew performance: on-schedule completion, Fleetio vehicle inspections, late departures, go backs, and estimated vs. actual hours per job. The default data source is the `Install Log` tab of the team's Google Sheet.

## Features
- Sidebar filters for date range and crew members, plus adjustable KPI goals
- KPI cards with performance vs. goal
- Crew comparison bar charts with goal lines and a leaderboard
- Daily review: edit estimated hours and split a crew member's day across jobs with sliders that always total 100%
- Editable data table with checkbox KPIs and notes
- Save percentage, estimate, checkbox, and note edits back to the exact Google Sheet rows
- An individual crew scorecard
- Filtered-data CSV download

## Files
| File | Purpose |
|---|---|
| `app.py` | Streamlit layout, widgets, and charts |
| `data.py` | Loads and cleans the install log, computes hours and day splits |
| `metrics.py` | KPI calculations |
| `google_sheet.py` | Reads and updates only the Google Sheet `Install Log` tab |

## Google Sheet setup

Public viewer access is enough for the dashboard to read the `Install Log` tab through its
direct per-tab CSV export. Writing changes requires a Google Cloud service account:

1. Enable the Google Sheets API in a Google Cloud project and create a service-account key.
2. Share the Google Sheet with the service account's `client_email` as **Editor**.
3. In Streamlit Community Cloud, open the app's **Settings → Secrets** and add the service-account fields shown in `.streamlit/secrets.toml.example`.

Do not commit a real service-account key. Slider and table changes remain pending in the Streamlit session until **Save changes to Google Sheet** is clicked.

## Run locally
```
pip install -r requirements.txt
streamlit run app.py
```
