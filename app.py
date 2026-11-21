"""Install Crew KPI Dashboard - Streamlit app."""
import altair as alt
import pandas as pd
import streamlit as st

import data
import metrics

st.set_page_config(page_title="Install Crew KPI Dashboard", page_icon="🛠️", layout="wide")

if "overrides" not in st.session_state:
    st.session_state.overrides = {}


@st.cache_data
def load_sample():
    return data.clean(data.read_source())


def pct(v):
    return "No data" if pd.isna(v) else f"{v:.1f}%"


# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Data")
    source = st.radio("Data source", ["Sample data (Sinister Six)", "Upload my tracker"],
                      label_visibility="collapsed")
    if source == "Upload my tracker":
        upload = st.file_uploader("Install tracker (.xlsx or .csv)", type=["xlsx", "csv"],
                                  help="Uses the 'Install Log' sheet. Files stay in this "
                                       "session only and are not saved.")
        if upload is None:
            st.info("Upload a file to continue, or switch back to the sample data.")
            st.stop()
        try:
            log = data.clean(data.read_source(upload))
        except Exception as e:
            st.error(f"Could not read that file: {e}")
            st.stop()
    else:
        log = load_sample()

    worked_all = log[log["worked"]]
    if worked_all.empty:
        st.error("No rows with clocked hours were found.")
        st.stop()

    st.header("Filters")
    min_d, max_d = worked_all["date"].min().date(), worked_all["date"].max().date()
    picked = st.date_input("Date range", (min_d, max_d), min_value=min_d, max_value=max_d)
    start, end = (picked if len(picked) == 2 else (picked[0], picked[0]))
    crews = sorted(worked_all["crew"].unique())
    chosen = st.multiselect("Crew members", crews, default=crews)

    st.header("Goals")
    goal_sched = st.slider("On-schedule goal (%)", 50, 100, 90)
    goal_fleet = st.slider("Fleetio inspection goal (%)", 50, 100, 95)
    goal_eff = st.slider("Hours efficiency goal (%)", 50, 150, 100,
                         help="Estimated hours ÷ actual hours. Over 100% means faster than estimate.")
    goal_late = st.number_input("Max late departures", 0, 50, 0)

# ---------------- Data prep ----------------
log = data.apply_splits(log, st.session_state.overrides)
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
c[2].metric("Hours Efficiency", pct(team.efficiency_pct),
            None if pd.isna(team.efficiency_pct) else f"{team.efficiency_pct - goal_eff:+.1f} vs goal")
c[3].metric("Late Departures", int(team.late_departures),
            f"{int(team.late_departures - goal_late):+d} vs limit", delta_color="inverse")
c[4].metric("Go Backs / Remakes", int(team.callbacks), delta_color="off")
c[5].metric("Clocked Hours", f"{team.clocked_hours:,.0f}",
            f"{int(team.days)} crew-days", delta_color="off")

tab_cmp, tab_hours, tab_trend, tab_card, tab_data = st.tabs(
    ["📊 Crew Comparison", "⏱️ Hours & Day Splits", "📈 Trends", "👤 Crew Scorecard", "🗂️ Data"])

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

# ---------------- Hours & day splits ----------------
with tab_hours:
    st.subheader("Estimated vs. actual hours")
    st.caption("Actual hours = clocked hours × % of day on that job (drive time is included). "
               "Only jobs with an estimate are compared.")
    hrs = (by_crew.reset_index()[["crew", "est_hours", "actual_hours"]]
           .melt("crew", var_name="type", value_name="hours"))
    hrs["type"] = hrs["type"].map({"est_hours": "Estimated", "actual_hours": "Actual"})
    st.altair_chart(
        alt.Chart(hrs).mark_bar().encode(
            x=alt.X("crew:N", title=None),
            xOffset="type:N",
            y=alt.Y("hours:Q", title="Hours"),
            color=alt.Color("type:N", title=None,
                            scale=alt.Scale(range=["#9ca3af", "#2563eb"],
                                            domain=["Estimated", "Actual"])),
            tooltip=["crew", "type", alt.Tooltip("hours:Q", format=".1f")],
        ).properties(height=320), width="stretch")

    st.subheader("Split a day across jobs")
    split_days = (df[df["jobs_that_day"] > 1]
                  .groupby(["crew", "date"]).size().reset_index(name="jobs"))
    if split_days.empty:
        st.info("No days with more than one job in this filter.")
    else:
        st.caption(f"{len(split_days)} days with more than one job. They default to an even "
                   "split. Adjust a day below to match how the time was really spent.")
        labels = [f"{r.crew} · {r.date:%a %b %d} ({r.jobs} jobs)"
                  for r in split_days.itertuples()]
        pick = st.selectbox("Crew member and day", range(len(labels)),
                            format_func=lambda i: labels[i])
        sel = split_days.iloc[pick]
        day_rows = df[(df["crew"] == sel.crew) & (df["date"] == sel.date)]
        keys = day_rows["key"].tolist()
        clocked = day_rows["clocked_hours"].iloc[0]

        def save_split(keys=keys):
            vals = [st.session_state[f"split::{k}"] for k in keys[:-1]]
            total = sum(vals)
            if total > 100:
                vals = [v * 100 / total for v in vals]
            for k, v in zip(keys[:-1], vals):
                st.session_state.overrides[k] = round(v, 1)
            st.session_state.overrides[keys[-1]] = round(max(0, 100 - sum(vals)), 1)

        st.write(f"**Clocked that day:** {clocked:.2f} hrs")
        for row in day_rows.iloc[:-1].itertuples():
            st.slider(f"{row.job_name} ({row.job_number}) - % of day", 0, 100,
                      int(round(row.day_pct)), step=5, key=f"split::{row.key}",
                      on_change=save_split)
        last = day_rows.iloc[-1]
        st.write(f"**{last.job_name} ({last.job_number})** gets the rest: {last.day_pct:.0f}%")
        if sum(st.session_state.get(f"split::{k}", 0) for k in keys[:-1]) > 100:
            st.warning("Sliders add up to more than 100%, so they were scaled down to fit.")

        detail = day_rows[["job_name", "est_hours", "day_pct", "actual_hours"]].copy()
        detail["efficiency"] = detail["est_hours"] / detail["actual_hours"] * 100
        st.dataframe(detail, hide_index=True, width="stretch", column_config={
            "job_name": "Job", "est_hours": st.column_config.NumberColumn("Est. hrs", format="%.2f"),
            "day_pct": st.column_config.NumberColumn("% of day", format="%.0f%%"),
            "actual_hours": st.column_config.NumberColumn("Actual hrs", format="%.2f"),
            "efficiency": st.column_config.NumberColumn("Efficiency", format="%.0f%%")})

        b1, b2 = st.columns(2)
        if b1.button("Reset this day to even split"):
            for k in keys:
                st.session_state.overrides.pop(k, None)
                st.session_state.pop(f"split::{k}", None)
            st.rerun()
        if b2.button("Reset all splits"):
            st.session_state.overrides = {}
            for k in [k for k in st.session_state if str(k).startswith("split::")]:
                del st.session_state[k]
            st.rerun()
        st.caption(f"{len(st.session_state.overrides)} adjusted job-days. Splits last for this "
                   "session. Download from the Data tab to keep them (re-upload keeps your %).")

# ---------------- Trends ----------------
with tab_trend:
    wk = metrics.weekly(df)
    trend = wk.melt("week", ["on_schedule_pct", "fleetio_pct", "efficiency_pct"],
                    var_name="kpi", value_name="value").dropna()
    trend["kpi"] = trend["kpi"].map(metrics.KPI_LABELS)
    st.subheader("Weekly team KPIs")
    st.altair_chart(
        alt.Chart(trend).mark_line(point=True).encode(
            x=alt.X("week:T", title="Week of", axis=alt.Axis(format="%b %d")),
            y=alt.Y("value:Q", title="%"),
            color=alt.Color("kpi:N", title=None),
            tooltip=[alt.Tooltip("week:T", format="%b %d"), "kpi",
                     alt.Tooltip("value:Q", format=".1f")],
        ).properties(height=320), width="stretch")

    st.subheader("Clocked hours by week")
    daily_hrs = (df.groupby(["crew", "date"], as_index=False)["clocked_hours"].max())
    daily_hrs["week"] = daily_hrs["date"] - pd.to_timedelta(daily_hrs["date"].dt.weekday, unit="D")
    st.altair_chart(
        alt.Chart(daily_hrs).mark_bar().encode(
            x=alt.X("week:T", title="Week of", axis=alt.Axis(format="%b %d")),
            y=alt.Y("sum(clocked_hours):Q", title="Hours"),
            color=alt.Color("crew:N", title="Crew"),
            tooltip=["crew", alt.Tooltip("sum(clocked_hours):Q", format=".1f", title="hours")],
        ).properties(height=300), width="stretch")

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
                None if pd.isna(me.efficiency_pct) or pd.isna(team.efficiency_pct)
                else f"{me.efficiency_pct - team.efficiency_pct:+.1f} vs team")
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
            "day_pct": st.column_config.NumberColumn("% of day", format="%.0f%%"),
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
    st.dataframe(df.drop(columns=["key", "worked"]), hide_index=True, width="stretch")
    st.download_button("Download filtered data (CSV)", data.export(df),
                       "crew_kpi_data.csv", "text/csv")
    with st.expander("How the numbers are calculated"):
        st.markdown(
            "- **On-Schedule %**: share of assignments marked *Work Completed on Schedule*.\n"
            "- **Fleetio %**: AM + PM inspections done ÷ inspections expected (2 per day worked).\n"
            "- **Estimated hours (per person, per day)**: job estimate ÷ days scheduled on "
            "the job ÷ crew size.\n"
            "- **Actual hours**: clocked hours × % of day on that job. Days with more than one "
            "job split evenly unless adjusted.\n"
            "- **Hours Efficiency %**: estimated ÷ actual hours, for jobs that have an estimate. "
            "Over 100% means faster than estimated.\n"
            "- Days and late departures count once per person per day.")
