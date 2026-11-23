"""Install Crew KPI Dashboard - Streamlit app."""
import altair as alt
import pandas as pd
import streamlit as st

import data
import google_sheet
import metrics

st.set_page_config(page_title="Install Crew KPI Dashboard", page_icon="🛠️", layout="wide")

for name, default in [("overrides", {}), ("est_overrides", {}), ("flag_overrides", {}),
                      ("notes_overrides", {}), ("est_version", 0)]:
    if name not in st.session_state:
        st.session_state[name] = default


@st.cache_data(ttl=300)
def load_google_sheet():
    raw = google_sheet.read_install_log()
    return data.clean(raw), google_sheet.percentage_source(raw)


def pct(v):
    return "No data" if pd.isna(v) else f"{v:.1f}%"


# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Data")
    try:
        log, (percentage_header, percentage_letter) = load_google_sheet()
    except Exception as e:
        st.error(f"Could not load the Google Sheet: {e}")
        st.stop()
    if percentage_header:
        st.caption(f"Install Log · percentages: {percentage_header} "
                   f"(column {percentage_letter})")
    else:
        st.warning("No Day Allocation % column was found; multi-job days will start evenly split.")
    if st.button("Refresh Google Sheet", width="stretch"):
        load_google_sheet.clear()
        st.rerun()

    worked_all = log[log["worked"]]
    if worked_all.empty:
        st.error("No rows with clocked hours were found.")
        st.stop()

    st.header("Filters")
    # Let users select every dated Install Log row, even when clocked hours are blank/zero.
    # KPI calculations below remain restricted to worked rows.
    min_d, max_d = log["date"].min().date(), log["date"].max().date()
    picked = st.date_input("Date range", (min_d, max_d), min_value=min_d, max_value=max_d)
    start, end = (picked if len(picked) == 2 else (picked[0], picked[0]))
    crews = sorted(worked_all["crew"].unique())
    chosen = st.multiselect("Crew members", crews, default=crews)

    st.header("Goals")
    goal_sched = st.slider("On-schedule goal (%)", 50, 100, 90)
    goal_fleet = st.slider("Fleetio inspection goal (%)", 50, 100, 95)
    goal_eff = st.slider("Hours efficiency goal (%)", 50, 150, 100,
                         help="Per crew member: estimated hours ÷ actual hours. "
                              "Over 100% means faster than estimate.")
    goal_late = st.number_input("Max late departures", 0, 50, 0)

# ---------------- Data prep ----------------
log = data.apply_edits(log, st.session_state.overrides, st.session_state.est_overrides,
                      st.session_state.flag_overrides, st.session_state.notes_overrides)
mask = (log["worked"] & log["crew"].isin(chosen)
        & log["date"].between(pd.Timestamp(start), pd.Timestamp(end)))
df = log[mask]

st.title("🛠️ Install Crew KPI Dashboard")
st.caption(f"{start:%b %d, %Y} to {end:%b %d, %Y} · {len(chosen)} crew members · "
           f"{df['job_number'].nunique()} jobs · {len(df)} assignments")

if df.empty:
    st.warning("No worked assignments match these filters.")
    st.stop()

team = metrics.summarize(df).iloc[0]
by_crew = metrics.summarize(df, by="crew")

# ---------------- KPI cards ----------------
c = st.columns(6)
c[0].metric("On-Schedule", pct(team.on_schedule_pct),
            None if pd.isna(team.on_schedule_pct) else f"{team.on_schedule_pct - goal_sched:+.1f} vs goal")
c[1].metric("Fleetio Inspections", pct(team.fleetio_pct),
            None if pd.isna(team.fleetio_pct) else f"{team.fleetio_pct - goal_fleet:+.1f} vs goal")
c[2].metric("Job Delays", int(team.job_delays), delta_color="off")
c[3].metric("Late Departures", int(team.late_departures),
            f"{int(team.late_departures - goal_late):+d} vs limit", delta_color="inverse")
c[4].metric("Go Backs / Remakes", int(team.callbacks), delta_color="off")
c[5].metric("Clocked Hours", f"{team.clocked_hours:,.0f}",
            f"{int(team.days)} crew-days", delta_color="off")

tab_cmp, tab_hours, tab_card, tab_data = st.tabs(
    ["📊 Crew Comparison", "⏱️ Hours & Estimates", "👤 Crew Scorecard", "🗂️ Data"])

# ---------------- Crew comparison ----------------
with tab_cmp:
    goals = {"on_schedule_pct": goal_sched, "fleetio_pct": goal_fleet,
             "efficiency_pct": goal_eff, "late_departures": goal_late}
    kpi = st.selectbox("KPI", list(metrics.KPI_LABELS),
                       format_func=metrics.KPI_LABELS.get)
    chart_df = by_crew.reset_index()[["crew", kpi]].dropna()
    bars = alt.Chart(chart_df).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X(f"{kpi}:Q", title=metrics.KPI_LABELS[kpi]),
        y=alt.Y("crew:N", sort="-x", title=None),
        color=alt.Color("crew:N", legend=None),
        tooltip=["crew", alt.Tooltip(f"{kpi}:Q", format=".1f")],
    )
    text = bars.mark_text(align="left", dx=4).encode(text=alt.Text(f"{kpi}:Q", format=".1f"),
                                                     color=alt.value("gray"))
    layers = bars + text
    if kpi in goals:
        layers += alt.Chart(pd.DataFrame({"goal": [goals[kpi]]})).mark_rule(
            color="red", strokeDash=[6, 4], size=2).encode(x="goal:Q")
    st.altair_chart(layers.properties(height=320), width="stretch")
    if kpi in goals:
        st.caption("Red dashed line = goal (set in the sidebar).")

    st.subheader("Leaderboard")
    board = by_crew.sort_values("on_schedule_pct", ascending=False).reset_index()
    board["Status"] = [
        "✅" if (metrics.goal_status(r.on_schedule_pct, goal_sched) == "On target"
                 and metrics.goal_status(r.fleetio_pct, goal_fleet) != "Below goal"
                 and r.late_departures <= goal_late) else "⚠️"
        for r in board.itertuples()]
    st.dataframe(
        board[["Status", "crew", "days", "assignments", "on_schedule_pct", "fleetio_pct",
               "efficiency_pct", "late_departures", "callbacks", "job_delays", "clocked_hours"]],
        hide_index=True, width="stretch",
        column_config={
            "crew": "Crew member", "days": "Days", "assignments": "Assignments",
            "on_schedule_pct": st.column_config.ProgressColumn("On-Schedule", format="%.1f%%",
                                                               min_value=0, max_value=100),
            "fleetio_pct": st.column_config.ProgressColumn("Fleetio", format="%.1f%%",
                                                           min_value=0, max_value=100),
            "efficiency_pct": st.column_config.NumberColumn("Efficiency", format="%.1f%%"),
            "late_departures": "Late", "callbacks": "Go Backs/Remakes",
            "job_delays": "Delays", "clocked_hours": st.column_config.NumberColumn(
                "Clocked hrs", format="%.1f"),
        })
    st.caption("✅ = meets on-schedule and Fleetio goals and the late departure limit.")

# ---------------- Hours & estimates ----------------
def rebalance(changed, group):
    """Keep a crew member's sliders for one day summing to 100%."""
    ss = st.session_state
    others = [k for k in group if k != changed]
    remaining = round(100.0 - ss[f"split::{changed}"], 2)
    current = [ss.get(f"split::{k}", 0) for k in others]
    weights = ([c / sum(current) for c in current] if sum(current) > 0
               else [1 / len(others)] * len(others))
    allocations = [round(remaining * weight, 2) for weight in weights[:-1]]
    allocations.append(round(remaining - sum(allocations), 2))
    for k, v in zip(others, allocations):
        ss[f"split::{k}"] = v
    for k in group:
        ss.overrides[k] = ss[f"split::{k}"]


def even_split(n):
    """Two-decimal percentages for n jobs that add up to exactly 100."""
    base = [round(100 / n, 2)] * (n - 1)
    return base + [round(100 - sum(base), 2)]


def normalized_split(values):
    """Preserve sheet allocations while normalizing rounding drift to exactly 100%."""
    values = [max(0.0, float(value)) for value in values]
    total = sum(values)
    if total <= 0:
        return even_split(len(values))
    scaled = [round(value * 100 / total, 2) for value in values[:-1]]
    return scaled + [round(100 - sum(scaled), 2)]


def save_inline_estimate(key):
    st.session_state.est_overrides[key] = st.session_state[f"est::{key}"]
    st.session_state.est_version += 1


def clear_widgets(prefix, keys=None):
    for k in [k for k in st.session_state if str(k).startswith(prefix)]:
        if keys is None or k[len(prefix):] in keys:
            del st.session_state[k]


with tab_hours:
    eff = by_crew["efficiency_pct"]
    st.markdown("**Hours efficiency by crew member** (estimated ÷ actual)")
    ec = st.columns(len(eff))
    for col, (name, val) in zip(ec, eff.items()):
        col.metric(name, pct(val), None if pd.isna(val) else f"{val - goal_eff:+.0f} vs goal")

    hrs = (by_crew.reset_index()[["crew", "est_hours", "actual_hours"]]
           .melt("crew", var_name="type", value_name="hours"))
    hrs["type"] = hrs["type"].map({"est_hours": "Estimated", "actual_hours": "Actual"})
    st.altair_chart(
        alt.Chart(hrs).mark_bar().encode(
            x=alt.X("crew:N", title=None, axis=alt.Axis(labelAngle=0)),
            xOffset="type:N",
            y=alt.Y("hours:Q", title="Hours"),
            color=alt.Color("type:N", title=None,
                            scale=alt.Scale(range=["#9ca3af", "#2563eb"],
                                            domain=["Estimated", "Actual"])),
            tooltip=["crew", "type", alt.Tooltip("hours:Q", format=".1f")],
        ).properties(height=280), width="stretch")

    st.subheader("Daily review")
    st.caption("Pick a day to see every job by crew member. Correct the estimated hours, and "
               "when someone worked more than one job, drag the sliders to split their clocked "
               "hours (drive time included). Each person's sliders always add up to 100%.")
    days = df.groupby("date")["job_number"].count().sort_index()
    day = st.selectbox("Date", days.index, index=len(days) - 1,
                       format_func=lambda d: f"{d:%a %b %d, %Y}  ·  {days[d]} assignments")
    today = df[df["date"] == day]

    widths = [3, 1.3, 1.1, 1.1, 1.1, 3.4]
    for crew_name, rows in today.groupby("crew", sort=True):
        keys = rows["key"].tolist()
        clocked = rows["clocked_hours"].iloc[0]
        with st.container(border=True):
            st.markdown(f"**{crew_name}** · {clocked:.2f} hrs clocked · "
                        f"{len(rows)} job{'s' if len(rows) > 1 else ''}")
            head = st.columns(widths)
            for col, label in zip(head, ["Job", "Est. hrs ✏️", "Actual hrs", "Efficiency",
                                         "Truck", "% of day"]):
                col.caption(label)
            if len(rows) > 1:
                start = normalized_split(rows["day_pct"].tolist())
                for k, v in zip(keys, start):
                    st.session_state.setdefault(f"split::{k}", v)
            for row in rows.itertuples():
                c = st.columns(widths, vertical_alignment="center")
                c[0].write(row.job_number if row.job_name == row.job_number
                           else f"{row.job_name} ({row.job_number})")
                st.session_state.setdefault(
                    f"est::{row.key}", float(0 if pd.isna(row.est_hours) else row.est_hours))
                c[1].number_input("Est. hrs", min_value=0.0, step=0.25,
                                  format="%.2f", key=f"est::{row.key}",
                                  label_visibility="collapsed",
                                  on_change=save_inline_estimate, args=(row.key,))
                c[2].write(f"{row.actual_hours:.2f}")
                c[3].write("n/a" if pd.isna(row.est_hours) or not row.actual_hours
                           else f"{row.est_hours / row.actual_hours * 100:.0f}%")
                c[4].write(row.truck)
                if len(rows) > 1:
                    c[5].slider("% of day", 0.0, 100.0, step=0.01,
                                key=f"split::{row.key}",
                                label_visibility="collapsed", format="%.2f%%",
                                on_change=rebalance, args=(row.key, keys))
                else:
                    c[5].write("100%")

    b1, b2, b3 = st.columns([1, 1, 2])
    if b1.button("Reset splits for this day"):
        day_keys = today["key"].tolist()
        for k in day_keys:
            st.session_state.overrides.pop(k, None)
        clear_widgets("split::", set(day_keys))
        st.rerun()
    if b2.button("Reset all splits"):
        st.session_state.overrides = {}
        clear_widgets("split::")
        st.rerun()
    b3.caption(f"{len(st.session_state.overrides)} job-day splits and "
               f"{len(st.session_state.est_overrides)} estimates adjusted. Changes last for this "
               "session until you save them from the Data tab.")

    with st.expander("Edit all estimates in a table"):
        ed_crew = st.selectbox("Show rows for", ["All crew"] + sorted(df["crew"].unique()),
                               key="ed_crew")
        view = df if ed_crew == "All crew" else df[df["crew"] == ed_crew]
        table = view[["key", "date", "crew", "job_name", "est_hours", "clocked_hours",
                      "day_pct", "actual_hours", "est_edited"]].reset_index(drop=True)
        table["efficiency"] = (table["est_hours"] / table["actual_hours"] * 100).round(0)
        editor_key = f"est_editor_{st.session_state.est_version}"

        def save_estimates(keys=table["key"].tolist(), editor_key=editor_key):
            changed = []
            for i, change in st.session_state[editor_key]["edited_rows"].items():
                if "est_hours" in change:
                    st.session_state.est_overrides[keys[int(i)]] = change["est_hours"]
                    changed.append(keys[int(i)])
            clear_widgets("est::", set(changed))
            st.session_state.est_version += 1

        st.data_editor(
            table, key=editor_key, on_change=save_estimates, hide_index=True, width="stretch",
            height=380, disabled=[c for c in table.columns if c != "est_hours"],
            column_config={
                "key": None,
                "date": st.column_config.DateColumn("Date", format="ddd MMM D"),
                "crew": "Crew member", "job_name": "Job",
                "est_hours": st.column_config.NumberColumn("Est. hrs ✏️", min_value=0, step=0.25,
                                                           format="%.2f"),
                "clocked_hours": st.column_config.NumberColumn("Clocked", format="%.2f"),
                "day_pct": st.column_config.NumberColumn("% of day", format="%.2f%%"),
                "actual_hours": st.column_config.NumberColumn("Actual hrs", format="%.2f"),
                "est_edited": st.column_config.CheckboxColumn("Edited"),
                "efficiency": st.column_config.NumberColumn("Efficiency", format="%.0f%%"),
            })
        if st.button("Reset all estimates"):
            st.session_state.est_overrides = {}
            st.session_state.est_version += 1
            clear_widgets("est::")
            st.rerun()

# ---------------- Crew scorecard ----------------
with tab_card:
    who = st.selectbox("Crew member", sorted(df["crew"].unique()))
    me = by_crew.loc[who]
    st.subheader(f"{who}")
    m = st.columns(4)
    m[0].metric("On-Schedule", pct(me.on_schedule_pct),
                None if pd.isna(me.on_schedule_pct) or pd.isna(team.on_schedule_pct)
                else f"{me.on_schedule_pct - team.on_schedule_pct:+.1f} vs team")
    m[1].metric("Fleetio", pct(me.fleetio_pct),
                None if pd.isna(me.fleetio_pct) or pd.isna(team.fleetio_pct)
                else f"{me.fleetio_pct - team.fleetio_pct:+.1f} vs team")
    m[2].metric("Hours Efficiency", pct(me.efficiency_pct),
                None if pd.isna(me.efficiency_pct) else f"{me.efficiency_pct - goal_eff:+.1f} vs goal")
    m[3].metric("Late Departures", int(me.late_departures), delta_color="off")

    st.markdown(
        f"- **{int(me.days)}** days worked, **{int(me.assignments)}** assignments on "
        f"**{int(me.jobs)}** jobs\n"
        f"- **{me.clocked_hours:.1f}** clocked hours, **{int(me.callbacks)}** go backs / "
        f"remakes / repairs, **{int(me.job_delays)}** job delays")

    mine = df[df["crew"] == who].sort_values("date", ascending=False)
    st.dataframe(
        mine[["date", "job_name", "truck", "est_hours", "clocked_hours", "day_pct",
              "actual_hours", "on_schedule", "fleetio_am", "fleetio_pm", "late_departure",
              "go_back"]],
        hide_index=True, width="stretch",
        column_config={
            "date": st.column_config.DateColumn("Date", format="ddd MMM D"),
            "job_name": "Job", "truck": "Truck",
            "est_hours": st.column_config.NumberColumn("Est. hrs", format="%.2f"),
            "clocked_hours": st.column_config.NumberColumn("Clocked", format="%.2f"),
            "day_pct": st.column_config.NumberColumn("% of day", format="%.2f%%"),
            "actual_hours": st.column_config.NumberColumn("Actual hrs", format="%.2f"),
            "on_schedule": st.column_config.CheckboxColumn("On sched."),
            "fleetio_am": st.column_config.CheckboxColumn("Fleetio AM"),
            "fleetio_pm": st.column_config.CheckboxColumn("Fleetio PM"),
            "late_departure": st.column_config.CheckboxColumn("Late"),
            "go_back": st.column_config.CheckboxColumn("Go back"),
        })

# ---------------- Data ----------------
with tab_data:
    st.subheader("Filtered assignments")
    st.caption("Check or uncheck the KPI boxes and correct Est. hrs right in the table. "
               "You can also update notes. Every chart and KPI updates with your changes; "
               "Google Sheet edits are sent only when you click Save below.")
    flag_labels = {"on_schedule": "On schedule ✏️", "fleetio_am": "Fleetio AM ✏️",
                   "fleetio_pm": "Fleetio PM ✏️", "late_departure": "Late departure ✏️",
                   "job_delay": "Job delay ✏️", "repair": "Repair ✏️", "remake": "Remake ✏️",
                   "go_back": "Go back ✏️"}
    editable = list(flag_labels) + ["est_hours", "notes"]
    cols = (["key", "date", "crew", "job_name", "est_hours", "clocked_hours", "day_pct",
             "actual_hours"] + list(flag_labels)
            + ["notes", "job_number", "truck", "crew_size", "est_job_hours", "jobs_that_day"])
    if (df["job_name"] == df["job_number"]).all():   # job name is just the number
        cols.remove("job_number")
    grid = df[cols].reset_index(drop=True)
    grid_key = f"data_editor_{st.session_state.est_version}"

    def save_grid(keys=grid["key"].tolist(), grid_key=grid_key):
        changed_est = []
        for i, change in st.session_state[grid_key]["edited_rows"].items():
            row_key = keys[int(i)]
            for col, value in change.items():
                if col == "est_hours":
                    st.session_state.est_overrides[row_key] = value
                    changed_est.append(row_key)
                elif col in flag_labels:
                    st.session_state.flag_overrides[(row_key, col)] = bool(value)
                elif col == "notes":
                    st.session_state.notes_overrides[row_key] = value
        clear_widgets("est::", set(changed_est))
        st.session_state.est_version += 1

    st.data_editor(
        grid, key=grid_key, on_change=save_grid, hide_index=True, width="stretch", height=460,
        disabled=[c for c in grid.columns if c not in editable],
        column_config={
            "key": None,
            "date": st.column_config.DateColumn("Date", format="ddd MMM D"),
            "crew": "Crew member", "job_number": "Job #", "job_name": "Job", "truck": "Truck",
            "crew_size": "Crew size",
            "est_job_hours": st.column_config.NumberColumn("Job est. (total)", format="%.0f"),
            "est_hours": st.column_config.NumberColumn("Est. hrs ✏️", min_value=0, step=0.25,
                                                       format="%.2f"),
            "clocked_hours": st.column_config.NumberColumn("Clocked", format="%.2f"),
            "jobs_that_day": "Jobs that day",
            "day_pct": st.column_config.NumberColumn("% of day", format="%.2f%%"),
            "actual_hours": st.column_config.NumberColumn("Actual hrs", format="%.2f"),
            "notes": st.column_config.TextColumn("Notes ✏️", width="large"),
            **{c: st.column_config.CheckboxColumn(label) for c, label in flag_labels.items()},
        })

    pending = google_sheet.pending_count(
        st.session_state.overrides, st.session_state.est_overrides,
        st.session_state.flag_overrides, st.session_state.notes_overrides)
    st.subheader("Google Sheet sync")
    st.caption("Saves Day Allocation % slider changes, estimates, KPI checkboxes, and notes "
               "back to the same rows in the Install Log tab.")
    if st.button(f"Save {pending} change{'s' if pending != 1 else ''} to Google Sheet",
                 type="primary", disabled=pending == 0):
        try:
            credentials = dict(st.secrets["gcp_service_account"])
        except Exception:
            st.error("Write access is not configured. Add the gcp_service_account block "
                     "to Streamlit Secrets and share the sheet with its client_email as Editor.")
        else:
            try:
                with st.spinner("Saving changes to Install Log..."):
                    saved = google_sheet.save_edits(
                        credentials, log, st.session_state.overrides,
                        st.session_state.est_overrides, st.session_state.flag_overrides,
                        st.session_state.notes_overrides)
            except Exception as e:
                st.error(f"Could not save changes to Google Sheet: {e}")
            else:
                st.session_state.overrides = {}
                st.session_state.est_overrides = {}
                st.session_state.flag_overrides = {}
                st.session_state.notes_overrides = {}
                st.session_state.est_version += 1
                load_google_sheet.clear()
                st.success(f"Saved {saved} changes to Install Log.")
                st.rerun()

    d1, d2, d3 = st.columns([1.2, 1, 2])
    d1.download_button("Download filtered data (CSV)", data.export(df),
                       "crew_kpi_data.csv", "text/csv")
    if d2.button("Reset checkbox edits"):
        st.session_state.flag_overrides = {}
        st.session_state.notes_overrides = {}
        st.session_state.est_version += 1
        st.rerun()
    d3.caption(f"{len(st.session_state.flag_overrides)} checkbox edits, "
               f"{len(st.session_state.est_overrides)} estimate edits, "
               f"{len(st.session_state.notes_overrides)} note edits, and "
               f"{len(st.session_state.overrides)} percentage edits pending.")
    with st.expander("How the numbers are calculated"):
        st.markdown(
            "- **On-Schedule %**: share of assignments marked *Work Completed on Schedule*.\n"
            "- **Fleetio %**: AM + PM inspections done ÷ inspections expected (2 per day worked).\n"
            "- **Estimated hours (per person, per day)**: job estimate ÷ days scheduled on "
            "the job ÷ crew size, unless you edit it.\n"
            "- **Actual hours**: clocked hours × % of day on that job. Days with more than one "
            "job split evenly unless adjusted.\n"
            "- **Hours Efficiency %** (per crew member): estimated ÷ actual hours, for rows "
            "that have an estimate. Over 100% means faster than estimated.\n"
            "- Days, Fleetio and late departures count once per person per day.")
