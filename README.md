# Install Crew KPI Dashboard

A Streamlit dashboard for tracking sign install crew performance: on-schedule completion, Fleetio vehicle inspections, late departures, go backs, and estimated vs. actual hours per job.

The sample data is real install log structure with anonymized names (the crew are the Sinister Six) and generic project names.

## Features
- Sidebar filters for date range and crew members, plus adjustable KPI goals
- KPI cards with performance vs. goal
- Crew comparison bar charts with goal lines and a leaderboard
- Daily review: edit estimated hours and split a crew member's day across jobs with sliders that always total 100%
- Editable data table with checkbox KPIs
- An individual crew scorecard
- Upload your own tracker (.xlsx `Install Log` sheet or .csv) and download filtered data

## Files
| File | Purpose |
|---|---|
| `app.py` | Streamlit layout, widgets, and charts |
| `data.py` | Loads and cleans the install log, computes hours and day splits |
| `metrics.py` | KPI calculations |
| `data/sample_install_log.csv` | Anonymized sample data |

## Run locally
```
pip install -r requirements.txt
streamlit run app.py
```
