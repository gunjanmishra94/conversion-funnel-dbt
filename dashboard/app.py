"""Conversion funnel dashboard.

Three views on top of the dbt models:
  * Management:      what the funnel shows and where customers are lost.
  * Decisions:       what each modelling decision does to the numbers.
  * Reporting model: rep_conversion_funnel_monthly as dbt stores it.

Run `dbt build` first, then from this folder: streamlit run app.py
"""

import json
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "interview_assignment.duckdb"
RUN_RESULTS = ROOT / "target" / "run_results.json"

NAVY, BLUE, AMBER, GREY = "#2D4961", "#1877B2", "#E5A823", "#A9B8C4"
STAGES = [
    "Lead Created",
    "Lead Qualified",
    "Lead Converted",
    "Opportunity Won",
    "Subscription Active",
    "First Delivery",
]
CAMPAIGN_MONTHS = [pd.Timestamp("2024-09-01"), pd.Timestamp("2024-10-01")]
BACKLOG_MONTHS = [pd.Timestamp("2024-06-01"), pd.Timestamp("2024-07-01")]

st.set_page_config(page_title="From lead to first delivery", layout="wide")


# ---------------------------------------------------------------- data access


@st.cache_resource
def connection():
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data
def query(sql: str) -> pd.DataFrame:
    return connection().cursor().execute(sql).df()


def models_are_built() -> bool:
    found = query(
        """
        select count(*) as n
        from information_schema.tables
        where table_name in ('rep_conversion_funnel_monthly', 'int_lead_funnel_stages')
        """
    )
    return int(found["n"][0]) == 2


@st.cache_data
def load_leads() -> pd.DataFrame:
    """One row per lead: funnel flags from dbt plus a few facts for the charts."""
    return query(
        """
        with opportunities as (
            select
                lead_id,
                min(created_at) as opportunity_at,
                min(case when is_closed_won then last_stage_change_at end) as won_at
            from main_staging.stg_opportunities
            group by lead_id
        ),

        subscriptions as (
            select
                lead_id,
                -- one state per lead: Active wins over any other status
                case
                    when bool_or(is_active) then 'Active'
                    else min(subscription_status)
                end as subscription_state
            from main_staging.stg_subscriptions
            where lead_id is not null
            group by lead_id
        ),

        first_deliveries as (
            select s.lead_id, min(d.created_at) as first_delivery_at
            from main_staging.stg_subscriptions as s
            inner join main_staging.stg_deliveries as d
                on s.subscription_id = d.subscription_id
            where s.is_active
            group by s.lead_id
        )

        select
            f.*,
            l.lead_status,
            coalesce(s.subscription_state, 'No subscription') as subscription_state,
            date_diff('day', f.created_at, o.opportunity_at) as days_to_opportunity,
            date_diff('day', f.created_at, o.won_at) as days_to_won,
            date_diff('day', f.created_at, d.first_delivery_at) as days_to_delivery
        from main_intermediate.int_lead_funnel_stages as f
        inner join main_staging.stg_leads as l on f.lead_id = l.lead_id
        left join opportunities as o on f.lead_id = o.lead_id
        left join subscriptions as s on f.lead_id = s.lead_id
        left join first_deliveries as d on f.lead_id = d.lead_id
        """
    )


def what_if_funnel(
    strict=True,
    drop_deleted=True,
    drop_duplicates=True,
    drop_future=True,
    normalise_stage=True,
    link_by_lead_key=True,
    require_account=False,
    delivered_only=False,
) -> list[int]:
    """Recomputes the six stage counts from the raw tables under the given rules.

    With the defaults this reproduces rep_conversion_funnel_monthly.
    """
    live = "not IS_DELETED" if drop_deleted else "true"
    future = "and cast(CREATED_DATE as date) <= current_date" if drop_future else ""
    dedupe = (
        "qualify row_number() over (partition by ID order by CREATED_DATE) = 1"
        if drop_duplicates
        else ""
    )
    won = (
        "lower(regexp_replace(trim(o.STAGE_NAME), '\\s+', ' ', 'g')) = 'closed won'"
        if normalise_stage
        else "o.STAGE_NAME = 'Closed Won'"
    )
    link = "o.LEAD__C = l.ID" if link_by_lead_key else "o.ID = l.CONVERTED_OPPORTUNITY_ID"
    account = (
        "and s.PATIENT__C in (select ID from assignment.ACCOUNT)" if require_account else ""
    )
    delivered = "and d.STATUS__C = 'Delivered'" if delivered_only else ""

    def chain(*flags):
        return " and ".join(flags) if strict else flags[-1]

    counts = query(
        f"""
        with leads as (
            select * from assignment.LEAD where {live} {future} {dedupe}
        ),

        flags as (
            select
                l.STATUS = 'Qualified' as q,
                l.IS_CONVERTED as c,
                exists (
                    select 1 from assignment.OPPORTUNITY as o
                    where {live} and {link} and {won}
                ) as w,
                exists (
                    select 1 from assignment.SUBSCRIPTION__C as s
                    where {live} and s.LEAD__C = l.ID and s.STATUS__C = 'Active' {account}
                ) as a,
                exists (
                    select 1
                    from assignment.SUBSCRIPTION__C as s
                    inner join assignment.DELIVERY__C as d on s.ID = d.SUBSCRIPTION__C
                    where
                        not (s.IS_DELETED and {str(drop_deleted).lower()})
                        and not (d.IS_DELETED and {str(drop_deleted).lower()})
                        and s.LEAD__C = l.ID
                        and s.STATUS__C = 'Active' {account} {delivered}
                ) as d
            from leads as l
        )

        select
            count(*) as s1,
            count(*) filter (where q) as s2,
            count(*) filter (where {chain('q', 'c')}) as s3,
            count(*) filter (where {chain('q', 'c', 'w')}) as s4,
            count(*) filter (where {chain('q', 'c', 'w', 'a')}) as s5,
            count(*) filter (where {chain('q', 'c', 'w', 'a', 'd')}) as s6
        from flags
        """
    )
    return [int(v) for v in counts.iloc[0]]


# -------------------------------------------------------------------- helpers

INK, MUTED, PALE = "#1A171B", "#5B7083", "#E3E8EC"
PENDING_STATES = ["Waiting for Approval", "Draft", "On-Hold"]
STATE_ORDER = [
    "Active",
    "Waiting for Approval",
    "Draft",
    "On-Hold",
    "Cancelled",
    "Completed",
    "No subscription",
]


def funnel_counts(leads: pd.DataFrame) -> list[int]:
    return [int(leads[f"reached_step_{n}"].sum()) for n in range(1, 7)]


def pct(part, whole) -> float | None:
    return round(part * 100 / whole, 1) if whole else None


def funnel_table(counts: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Stage": STAGES,
            "Leads": counts,
            "From previous stage (%)": [None]
            + [pct(counts[i], counts[i - 1]) for i in range(1, 6)],
        }
    )


def show(chart, container=st):
    """Renders a chart with the shared look: no grid, no frame."""
    container.altair_chart(
        chart.configure_axis(grid=False, labelColor=MUTED, titleColor=MUTED)
        .configure_view(stroke=None)
        .configure_legend(labelColor=INK, titleColor=MUTED),
        use_container_width=True,
    )


def funnel_chart(counts: list[int]):
    """Centred bars, so the narrowing reads as a funnel. Each bar is labelled
    with its count and its share of the step before."""
    top = counts[0]
    data = pd.DataFrame(
        {
            "Stage": STAGES,
            "Leads": counts,
            "left": [-n / 2 for n in counts],
            "right": [n / 2 for n in counts],
            "label": [f"{counts[0]:,}"]
            + [
                f"{counts[i]:,}   ({pct(counts[i], counts[i - 1])}% of the step before)"
                for i in range(1, 6)
            ],
        }
    )
    base = alt.Chart(data).encode(
        y=alt.Y("Stage:N", sort=STAGES, title=None, axis=alt.Axis(labelLimit=220, ticks=False, domain=False))
    )
    bars = base.mark_bar(color=BLUE, cornerRadius=3, height=34).encode(
        x=alt.X("left:Q", axis=None, scale=alt.Scale(domain=[-top / 2, top * 1.15])),
        x2="right:Q",
        tooltip=["Stage", "Leads"],
    )
    labels = base.mark_text(align="left", dx=10, color=INK).encode(x="right:Q", text="label:N")
    return (bars + labels).properties(height=300)


def trend_chart(monthly: pd.DataFrame, measure: str, mark_campaign: bool):
    """Line over time, with the campaign months shaded."""
    base = alt.Chart(monthly).encode(
        x=alt.X("lead_month:T", title=None, axis=alt.Axis(format="%b %y", labelOverlap=True)),
        y=alt.Y(f"{measure}:Q", title=measure),
        tooltip=[alt.Tooltip("lead_month:T", title="Month", format="%B %Y"), f"{measure}:Q"],
    )
    layers = [base.mark_line(color=BLUE, strokeWidth=2), base.mark_point(color=BLUE, filled=True, size=55, opacity=1)]
    if mark_campaign:
        band = (
            alt.Chart(pd.DataFrame({"start": [pd.Timestamp("2024-08-16")], "end": [pd.Timestamp("2024-10-16")]}))
            .mark_rect(color=AMBER, opacity=0.2)
            .encode(x="start:T", x2="end:T")
        )
        layers.insert(0, band)
    return alt.layer(*layers).properties(height=170)


BRAND_COLOURS = {"Prosenio": BLUE, "Sanubi": AMBER, "PflegeBox": "#B8336A", "SanBox": GREY}


def brand_profile_chart(view: pd.DataFrame):
    """Each brand's pass rate at the four steps, to show where a gap opens.

    A brand is drawn only if every step rests on at least 30 leads; smaller
    bases swing too much to compare. Returns None when no brand qualifies.
    """
    steps = ["Qualified", "Converted", "Deal won", "Subscription active"]
    rows = []
    for brand, group in view.groupby("brand"):
        c = funnel_counts(group)
        if min(c[:4]) < 30:
            continue
        for i, step in enumerate(steps, start=1):
            rows.append({"Brand": brand, "Step": step, "Share that pass (%)": pct(c[i], c[i - 1])})
    if not rows:
        return None
    data = pd.DataFrame(rows)
    brands = [b for b in BRAND_COLOURS if b in set(data["Brand"])]
    base = alt.Chart(data).encode(
        x=alt.X("Step:N", sort=steps, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Share that pass (%):Q", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color(
            "Brand:N",
            scale=alt.Scale(domain=brands, range=[BRAND_COLOURS[b] for b in brands]),
            title=None,
            legend=alt.Legend(orient="top"),
        ),
        tooltip=["Brand", "Step", "Share that pass (%)"],
    )
    lines = base.mark_line(strokeWidth=2.5) + base.mark_point(filled=True, size=80, opacity=1)
    return lines.properties(height=320)


def state_bar_chart(won: pd.DataFrame):
    """Part of a whole: one bar split into active, pending and ended."""
    grouped = won["subscription_state"].map(
        lambda s: "Active" if s == "Active" else "Pending" if s in PENDING_STATES else "Ended or none"
    )
    order = ["Active", "Pending", "Ended or none"]
    counts = grouped.value_counts().reindex(order, fill_value=0)
    data = pd.DataFrame({"Group": order, "Won deals": counts.values})
    data["end"] = data["Won deals"].cumsum()
    data["start"] = data["end"] - data["Won deals"]
    data["middle"] = (data["start"] + data["end"]) / 2
    data["label"] = [f"{g}: {n} ({pct(n, len(won))}%)" for g, n in zip(order, counts.values)]
    data = data[data["Won deals"] > 0]
    base = alt.Chart(data)
    bar = base.mark_bar(height=46, stroke="#FFFCFC", strokeWidth=2, cornerRadius=3).encode(
        x=alt.X("start:Q", axis=None),
        x2="end:Q",
        color=alt.Color("Group:N", scale=alt.Scale(domain=order, range=[BLUE, AMBER, GREY]), legend=None),
        tooltip=["Group", "Won deals"],
    )
    labels = base.mark_text(dy=-36, color=INK).encode(x="middle:Q", text="label:N")
    return (bar + labels).properties(height=110)


def waiting_chart(won: pd.DataFrame, months: list):
    """Won deals still waiting for approval, per month the lead arrived."""
    waiting = won[won["subscription_state"] == "Waiting for Approval"].groupby("lead_month").size()
    # every month of the selection gets a bar, so the months with none show as zero
    data = pd.DataFrame({"lead_month": months, "Waiting": waiting.reindex(months, fill_value=0).values})
    data["Period"] = data["lead_month"].isin(BACKLOG_MONTHS).map({True: "June and July 2024", False: "Other months"})
    data["Month"] = data["lead_month"].dt.strftime("%b %y")
    base = alt.Chart(data).encode(
        x=alt.X("Month:N", sort=list(data["Month"]), title="Month the lead arrived", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Waiting:Q", title="Won deals waiting for approval"),
    )
    bars = base.mark_bar(size=22, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        color=alt.Color(
            "Period:N",
            scale=alt.Scale(domain=["June and July 2024", "Other months"], range=[AMBER, BLUE]),
            legend=alt.Legend(title=None, orient="top"),
        ),
        tooltip=["Month", alt.Tooltip("Waiting:Q", title="Waiting for approval")],
    )
    # only the months that have waiting deals get a number; a row of zeros reads as noise
    numbers = base.transform_filter(alt.datum.Waiting > 0).mark_text(dy=-10, color=INK).encode(text="Waiting:Q")
    return (bars + numbers).properties(height=220)


def state_heatmap(won: pd.DataFrame):
    """Month by subscription state. Darker means more won deals."""
    data = (
        won.assign(Month=won["lead_month"].dt.strftime("%Y-%m"))
        .groupby(["Month", "subscription_state"])
        .size()
        .reset_index(name="Won deals")
        .rename(columns={"subscription_state": "Subscription"})
    )
    base = alt.Chart(data).encode(
        x=alt.X("Month:N", title="Month the lead arrived", axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("Subscription:N", sort=STATE_ORDER, title=None, axis=alt.Axis(labelLimit=200)),
    )
    cells = base.mark_rect(stroke="#FFFCFC", strokeWidth=2).encode(
        color=alt.Color("Won deals:Q", scale=alt.Scale(scheme="blues"), title="Won deals"),
        tooltip=["Month", "Subscription", "Won deals"],
    )
    numbers = base.mark_text().encode(
        text="Won deals:Q",
        color=alt.condition(alt.datum["Won deals"] > float(data["Won deals"].max()) * 0.55, alt.value("#FFFCFC"), alt.value(INK)),
    )
    return (cells + numbers).properties(height=280)


def timeline_chart(days: list[int]):
    """The journey of a typical customer on a day axis."""
    events = pd.DataFrame(
        {
            "day": [0] + days,
            "event": ["Lead arrives", "Sales case opened", "Deal won", "First delivery"],
            "when": ["Day 0"] + [f"Day {d}" for d in days],
            "above": [True, False, True, False],
        }
    )
    scale = alt.Scale(domain=[-4, max(days) + 6])
    line = (
        alt.Chart(pd.DataFrame({"start": [0], "end": [max(days)]}))
        .mark_rule(color=GREY, strokeWidth=4)
        .encode(x=alt.X("start:Q", axis=None, scale=scale), x2="end:Q")
    )
    base = alt.Chart(events).encode(x=alt.X("day:Q", axis=None, scale=scale))
    dots = base.mark_point(filled=True, size=260, color=BLUE, opacity=1, stroke="#FFFCFC", strokeWidth=2).encode(
        tooltip=["event", "when"]
    )
    layers = [line, dots]
    for above in (True, False):
        side = base.transform_filter(alt.datum.above == above)
        layers.append(side.mark_text(dy=-34 if above else 24, fontWeight="bold", color=INK).encode(text="event:N"))
        layers.append(side.mark_text(dy=-18 if above else 40, color=MUTED).encode(text="when:N"))
    return alt.layer(*layers).properties(height=130)


def waterfall_chart(today: int, gains: list[tuple[str, int]]):
    """Bridge from today's customers to the possible total."""
    rows, running = [{"Step": "Customers today", "start": 0, "end": today, "Kind": "Today", "label": f"{today}"}], today
    for name, gain in gains:
        rows.append({"Step": name, "start": running, "end": running + gain, "Kind": "Gain", "label": f"+{gain}"})
        running += gain
    rows.append({"Step": "Possible total", "start": 0, "end": running, "Kind": "Total", "label": f"{running}"})
    data = pd.DataFrame(rows)
    order = data["Step"].tolist()
    base = alt.Chart(data).encode(x=alt.X("Step:N", sort=order, title=None, axis=alt.Axis(labelAngle=0, labelLimit=220)))
    bars = base.mark_bar(cornerRadius=3, size=70).encode(
        y=alt.Y("start:Q", title="Customers"),
        y2="end:Q",
        color=alt.Color(
            "Kind:N", scale=alt.Scale(domain=["Today", "Gain", "Total"], range=[BLUE, AMBER, NAVY]), legend=None
        ),
        tooltip=["Step", alt.Tooltip("label:N", title="Customers")],
    )
    labels = base.mark_text(dy=-10, color=INK, fontWeight="bold").encode(y="end:Q", text="label:N")
    return (bars + labels).properties(height=300)


def difference_chart(comparison: pd.DataFrame):
    """Change against the model, per stage, around a zero line."""
    data = comparison.assign(label=comparison["Difference"].map(lambda d: f"{d:+d}"))
    base = alt.Chart(data).encode(y=alt.Y("Stage:N", sort=STAGES, title=None, axis=alt.Axis(labelLimit=220)))
    bars = base.mark_bar(height=22, cornerRadius=2).encode(
        x=alt.X("Difference:Q", title="Leads more or fewer than the model"),
        color=alt.condition(alt.datum.Difference > 0, alt.value(AMBER), alt.value(BLUE)),
        tooltip=["Stage", "Model", "Your settings", "Difference"],
    )
    labels = base.mark_text(color=INK, dx=alt.expr("datum.Difference < 0 ? -14 : 14")).encode(
        x="Difference:Q", text="label:N"
    )
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=MUTED).encode(x="x:Q")
    return (bars + labels + zero).properties(height=230)


def skipped_matrix(skipped: pd.DataFrame):
    """One row per lead, one column per stage: which conditions it meets."""
    conditions = {
        "is_qualified": "Qualified",
        "is_converted": "Converted",
        "has_won_opportunity": "Deal won",
        "has_active_subscription": "Subscription active",
        "has_delivery": "Delivery",
    }
    data = skipped.melt(
        id_vars=["lead_id"], value_vars=list(conditions), var_name="condition", value_name="met"
    )
    data["Stage"] = data["condition"].map(conditions)
    data["Condition"] = data["met"].map({True: "Met", False: "Not met"})
    return (
        alt.Chart(data)
        .mark_rect(stroke="#FFFCFC", strokeWidth=3, cornerRadius=3)
        .encode(
            x=alt.X("Stage:N", sort=list(conditions.values()), title=None, axis=alt.Axis(labelAngle=0, orient="top")),
            y=alt.Y("lead_id:N", title=None),
            color=alt.Color("Condition:N", scale=alt.Scale(domain=["Met", "Not met"], range=[BLUE, PALE]), title=None),
            tooltip=[alt.Tooltip("lead_id:N", title="Lead"), "Stage", "Condition"],
        )
        .properties(height=max(120, 28 * skipped["lead_id"].nunique()))
    )


# ----------------------------------------------------------- management view


def management_view(leads: pd.DataFrame):
    st.title("From lead to first delivery")
    st.caption(
        "Every lead is counted in the month it arrived. A customer is a lead with a won "
        "deal, an active subscription and at least one delivery."
    )

    with st.sidebar:
        st.header("Filters")
        brands = st.multiselect("Brand", sorted(leads["brand"].unique()), default=None)
        sources = st.multiselect("Lead source", sorted(leads["lead_source"].unique()))
        all_months = sorted(leads["lead_month"].unique())
        first, last = st.select_slider(
            "Month the lead arrived",
            options=all_months,
            value=(all_months[0], all_months[-1]),
            format_func=lambda m: pd.Timestamp(m).strftime("%b %Y"),
        )
        skip_campaign = st.checkbox("Leave out the autumn 2024 campaign months")

    view = leads[(leads["lead_month"] >= first) & (leads["lead_month"] <= last)]
    if brands:
        view = view[view["brand"].isin(brands)]
    if sources:
        view = view[view["lead_source"].isin(sources)]
    if skip_campaign:
        view = view[~view["lead_month"].isin(CAMPAIGN_MONTHS)]
    if view.empty:
        st.warning("No leads match these filters.")
        return

    counts = funnel_counts(view)
    tiles = st.columns(4)
    tiles[0].metric("Leads", f"{counts[0]:,}")
    tiles[1].metric("Customers", f"{counts[5]:,}")
    tiles[2].metric("Leads that become customers", f"{pct(counts[5], counts[0])}%")
    tiles[3].metric("Leads that are qualified", f"{pct(counts[1], counts[0])}%")

    # --- funnel
    st.subheader("The funnel")
    show(funnel_chart(counts))
    st.caption(
        "Each step up to an active subscription loses about half. Once a subscription "
        "is active, the delivery almost always follows."
    )
    with st.expander("Show as a table"):
        st.dataframe(funnel_table(counts), hide_index=True, width="stretch")

    # --- over time
    st.subheader("Leads and customers over time")
    monthly = (
        view.groupby("lead_month")
        .agg(Leads=("lead_id", "count"), Customers=("reached_step_6", "sum"))
        .reset_index()
    )
    campaign_shown = bool(monthly["lead_month"].isin(CAMPAIGN_MONTHS).any())
    # two charts instead of one: leads (~150 a month) and customers (~15) need their own scales
    show(
        alt.vconcat(
            trend_chart(monthly, "Leads", campaign_shown),
            trend_chart(monthly, "Customers", campaign_shown),
        )
    )
    campaign = leads[leads["lead_month"].isin(CAMPAIGN_MONTHS)]
    normal = leads[~leads["lead_month"].isin(CAMPAIGN_MONTHS)]
    untouched = lambda d: pct((d["lead_status"] == "New").sum(), len(d))
    st.caption(
        f"The shaded band is September and October 2024, when a paid campaign brought "
        f"{len(campaign):,} leads but only {int(campaign['reached_step_6'].sum())} customers. "
        f"{untouched(campaign)}% of the campaign leads still have the status New, against "
        f"{untouched(normal)}% in other months, so many of them were never worked."
    )

    # --- brands
    st.subheader("Brands")
    by_brand = pd.DataFrame(
        [
            {
                "Brand": brand,
                "Leads": c[0],
                "Customers": c[5],
                "Leads that become customers (%)": pct(c[5], c[0]),
            }
            for brand, c in ((b, funnel_counts(g)) for b, g in view.groupby("brand"))
        ]
    ).sort_values("Leads that become customers (%)", ascending=False)
    left, right = st.columns([3, 2])
    profile = brand_profile_chart(view)
    if profile is None:
        left.info("Too few leads per brand in this selection to compare the steps.")
    else:
        show(profile, left)
    right.dataframe(by_brand, hide_index=True, width="stretch")
    right.caption(
        "The chart shows the share of leads that pass each step, measured against the step "
        "before. The brands start level at qualification; the gap opens at conversion and "
        "at winning the deal. SanBox received leads only during the campaign months and has "
        "too few won deals to be drawn."
    )

    # --- after the sale
    st.subheader("After the sale")
    won = view[view["reached_step_4"]]
    if won.empty:
        st.info("No won deals in this selection.")
    else:
        st.markdown(f"**What became of the {len(won):,} won deals**")
        show(state_bar_chart(won))
        st.caption("Pending means waiting for approval, in draft or on hold.")
        waiting = won[won["subscription_state"] == "Waiting for Approval"]
        stuck = int(waiting["lead_month"].isin(BACKLOG_MONTHS).sum())
        st.markdown("**Won deals still waiting for approval**")
        show(waiting_chart(won, sorted(view["lead_month"].unique())))
        st.caption(
            f"{stuck} of the {len(waiting)} won deals waiting for approval come from leads that "
            "arrived in June and July 2024. The grid below shows every status by month."
        )
        show(state_heatmap(won))

    # --- speed
    st.subheader("How long it takes")
    customers = view[view["reached_step_6"]]
    if customers.empty:
        st.info("No customers in this selection.")
    else:
        days = [
            int(customers[field].dropna().median())
            for field in ("days_to_opportunity", "days_to_won", "days_to_delivery")
        ]
        show(timeline_chart(days))
        st.caption("Median days for leads that became customers. The brands do not differ here.")

    # --- simulator
    st.subheader("What would more customers take?")
    st.caption(
        "Simple arithmetic on all leads, ignoring the filters. It shows the size of each "
        "gap and is not a forecast."
    )
    rates = {b: funnel_counts(g) for b, g in normal.groupby("brand")}
    best = rates["Prosenio"][5] / rates["Prosenio"][0]
    gap = sum(rates[b][0] * best - rates[b][5] for b in ("Sanubi", "PflegeBox") if b in rates)
    pending = int(leads.loc[leads["reached_step_4"], "subscription_state"].isin(PENDING_STATES).sum())
    left, right = st.columns([2, 3])
    close_gap = left.slider("Sanubi and PflegeBox close this share of the gap to Prosenio (%)", 0, 100, 50, 5)
    activate = left.slider(f"Share of the {pending} pending won deals that become active (%)", 0, 100, 50, 5)
    show(
        waterfall_chart(
            funnel_counts(leads)[5],
            [("Brand gap closed", round(gap * close_gap / 100)), ("Pending deals activated", round(pending * activate / 100))],
        ),
        right,
    )


# ------------------------------------------------------------- decisions view


def decisions_view(leads: pd.DataFrame):
    st.title("Modelling decisions")
    st.caption(
        "What each decision behind rep_conversion_funnel_monthly does to the numbers. "
        "Everything on this page is recomputed from the raw tables."
    )

    chosen = what_if_funnel()
    model = query(
        """
        select funnel_step, sum("count") as n
        from main_reporting.rep_conversion_funnel_monthly
        group by funnel_step
        order by funnel_step
        """
    )["n"].astype(int).tolist()

    # --- cleaning
    st.subheader("1. From raw rows to valid leads")
    raw = query(
        """
        select
            count(*) as raw_rows,
            count(*) filter (where IS_DELETED) as deleted,
            count(*) filter (where not IS_DELETED and cast(CREATED_DATE as date) > current_date) as future,
            count(*) filter (where not IS_DELETED) - count(distinct ID) filter (where not IS_DELETED) as duplicates
        from assignment.LEAD
        """
    ).iloc[0].astype(int)
    valid = raw["raw_rows"] - raw["deleted"] - raw["duplicates"] - raw["future"]
    # the removals are too small to see as bars next to 3,000 rows, so: tiles
    tiles = st.columns(5)
    tiles[0].metric("Raw lead rows", f"{raw['raw_rows']:,}")
    tiles[1].metric("Soft-deleted", f"-{raw['deleted']}")
    tiles[2].metric("Duplicated IDs", f"-{raw['duplicates']}")
    tiles[3].metric("Dated in the future", f"-{raw['future']}")
    tiles[4].metric("Valid leads", f"{valid:,}")
    st.markdown(
        "- **Deleted rows** are removed in every table.\n"
        "- **Duplicates** differ only in creation time, by minutes. The earliest row is kept.\n"
        "- **Future-dated leads** would add cohort months that do not exist.\n"
        "- With these rules March 2024 gives 180 leads, 126 qualified and 80 converted, "
        "the example row in the assignment."
    )

    # --- what if
    st.subheader("2. What if a decision had gone the other way?")
    st.caption("The switches start at the rules the model uses. Change one and compare.")
    a, b, c = st.columns(3)
    options = dict(
        strict=a.toggle("Strict sequence", True, help="Off: each stage is counted by its own condition."),
        normalise_stage=a.toggle("Clean the stage name", True, help="Off: exact match on 'Closed Won'."),
        link_by_lead_key=a.toggle(
            "Link opportunities by OPPORTUNITY.LEAD__C", True, help="Off: use LEAD.CONVERTED_OPPORTUNITY_ID."
        ),
        drop_deleted=b.toggle("Remove soft-deleted rows", True),
        drop_duplicates=b.toggle("Remove duplicated lead IDs", True),
        drop_future=b.toggle("Remove future-dated leads", True),
        require_account=c.toggle("Require a valid patient account", False),
        delivered_only=c.toggle("Count only deliveries with status Delivered", False),
    )
    yours = what_if_funnel(**options)
    comparison = pd.DataFrame(
        {
            "Stage": STAGES,
            "Model": chosen,
            "Your settings": yours,
            "Difference": [y - m for y, m in zip(yours, chosen)],
        }
    )
    left, right = st.columns([2, 3])
    left.dataframe(comparison, hide_index=True, width="stretch")
    if comparison["Difference"].any():
        show(difference_chart(comparison), right)
    else:
        right.info("These settings give the same funnel as the model.")
    increases = [STAGES[i] for i in range(1, 6) if yours[i] > yours[i - 1]]
    if increases:
        st.warning("A later stage exceeds the one before it: " + ", ".join(increases) + ".")
    if chosen == model:
        st.caption("Check: the Model column equals the dbt table rep_conversion_funnel_monthly.")
    else:
        st.error("The recomputed funnel does not match the dbt table. Run `dbt build`.")

    # --- strict vs independent
    st.subheader("3. Leads that skip a stage")
    skipped = leads[~leads["is_stage_consistent"]].sort_values("lead_month")
    st.markdown(
        f"**{len(skipped)} of {len(leads):,} leads** meet the condition of a stage without all "
        "earlier ones. Each row is one lead; a pale cell to the left of a blue one is a "
        "skipped stage. The strict sequence counts these leads only up to their last "
        "consistent stage."
    )
    show(skipped_matrix(skipped))
    with st.expander("Show as a table"):
        st.dataframe(
            skipped[
                [
                    "lead_id",
                    "lead_month",
                    "brand",
                    "lead_status",
                    "is_qualified",
                    "is_converted",
                    "has_won_opportunity",
                    "has_active_subscription",
                    "has_delivery",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={"lead_month": st.column_config.DateColumn("lead_month", format="YYYY-MM")},
        )

    # --- data quality
    st.subheader("4. Data quality")
    issues = query(
        """
        select 'Lead IDs that appear twice' as issue, count(*) as rows
        from (select ID from assignment.LEAD group by ID having count(*) > 1)
        union all
        select 'Soft-deleted rows, all tables', (
            (select count(*) from assignment.LEAD where IS_DELETED)
            + (select count(*) from assignment.OPPORTUNITY where IS_DELETED)
            + (select count(*) from assignment.SUBSCRIPTION__C where IS_DELETED)
            + (select count(*) from assignment.DELIVERY__C where IS_DELETED)
        )
        union all
        select 'Leads dated in the future', count(*)
        from assignment.LEAD where cast(CREATED_DATE as date) > current_date
        union all
        select 'Opportunities with a misspelled Closed Won', count(*)
        from assignment.OPPORTUNITY
        where STAGE_NAME <> 'Closed Won'
            and lower(regexp_replace(trim(STAGE_NAME), '\\s+', ' ', 'g')) = 'closed won'
        union all
        select 'Subscriptions without a valid lead', count(*)
        from assignment.SUBSCRIPTION__C
        where LEAD__C is null or LEAD__C not in (select ID from assignment.LEAD)
        union all
        select 'Deliveries without a valid subscription', count(*)
        from assignment.DELIVERY__C
        where SUBSCRIPTION__C not in (select ID from assignment.SUBSCRIPTION__C)
        union all
        select 'Converted leads without an opportunity ID', count(*)
        from assignment.LEAD
        where IS_CONVERTED and CONVERTED_OPPORTUNITY_ID is null
        """
    )
    left, right = st.columns(2)
    left.markdown("**Found in the raw tables**")
    left.dataframe(issues, hide_index=True, width="stretch")
    right.markdown("**Latest dbt test run**")
    if RUN_RESULTS.exists():
        results = json.loads(RUN_RESULTS.read_text())["results"]
        tests = [r for r in results if r["unique_id"].startswith("test.")]
        if tests:
            status = pd.Series([r["status"] for r in tests]).value_counts()
            right.write(", ".join(f"{n} {s}" for s, n in status.items()))
            warned = pd.DataFrame(
                [
                    {"Test": r["unique_id"].split(".")[2], "Rows": r.get("failures")}
                    for r in tests
                    if r["status"] != "pass"
                ]
            )
            if not warned.empty:
                right.dataframe(warned, hide_index=True, width="stretch")
                right.caption("These warnings are intended: the raw problems stay visible.")
        else:
            right.info("The latest dbt run contained no tests. Run `dbt test`.")
    else:
        right.info("No dbt results found. Run `dbt build`.")

    # --- cohorts stay open
    st.subheader("5. Why a cohort is not finished when its month ends")
    days = leads.loc[leads["reached_step_6"], "days_to_delivery"].dropna().astype(int)
    late = query(
        """
        select max(date_diff('day', l.created_at, s.last_modified_at)) as days
        from main_staging.stg_leads as l
        inner join main_staging.stg_subscriptions as s on l.lead_id = s.lead_id
        """
    )["days"][0]
    tiles = st.columns(3)
    tiles[0].metric("Median days to first delivery", int(days.median()))
    tiles[1].metric("Longest", f"{int(days.max())} days")
    tiles[2].metric("Latest change to a subscription", f"{int(late)} days after its lead")
    show(
        alt.Chart(pd.DataFrame({"Days from lead to first delivery": days}))
        .mark_bar(color=BLUE)
        .encode(
            x=alt.X("Days from lead to first delivery:Q", bin=alt.Bin(step=5)),
            y=alt.Y("count():Q", title="Leads"),
            tooltip=[alt.Tooltip("count():Q", title="Leads")],
        )
        .properties(height=220)
    )
    st.caption(
        "Numbers for a past month keep changing for months, so recomputing only the "
        "newest month would miss updates."
    )


# --------------------------------------------------------- reporting model view


def reporting_table_view():
    st.title("Reporting model")
    st.caption(
        "The dbt model rep_conversion_funnel_monthly exactly as it is stored in "
        "main_reporting: one row per month and funnel step."
    )
    table = query(
        """
        select *
        from main_reporting.rep_conversion_funnel_monthly
        order by "month", funnel_step
        """
    )
    table["month"] = pd.to_datetime(table["month"]).dt.date
    table["conversion_from_previous_pct"] = table["conversion_from_previous_pct"].astype(float)

    months = sorted(table["month"].unique())
    with st.sidebar:
        st.header("Filters")
        chosen = st.multiselect(
            "Month",
            months,
            format_func=lambda m: m.strftime("%b %Y"),
            placeholder="All months",
        )
    shown = table[table["month"].isin(chosen)] if chosen else table

    tiles = st.columns(3)
    tiles[0].metric("Rows", f"{len(shown):,}")
    tiles[1].metric("Months", shown["month"].nunique())
    tiles[2].metric("Steps per month", shown["funnel_step"].nunique())
    st.dataframe(
        shown,
        hide_index=True,
        width="stretch",
        # fit the rows (35px each plus the header) so a short table has no empty grid
        height=min(460, 35 * (len(shown) + 1) + 3),
        column_config={
            "month": st.column_config.DateColumn("month", format="YYYY-MM-DD"),
            "conversion_from_previous_pct": st.column_config.NumberColumn(
                "conversion_from_previous_pct", format="%.1f"
            ),
        },
    )
    st.caption(
        "conversion_from_previous_pct is empty (NULL) for step 1, which has no previous step. "
        "March 2024 is the example from the assignment: 180, 126 (70.0), 80 (63.5)."
    )


# ----------------------------------------------------------------------- main


def main():
    if not DB_PATH.exists():
        st.error(f"Database not found at {DB_PATH}. Put interview_assignment.duckdb in data/.")
        return
    if not models_are_built():
        st.error("The dbt models are missing. Run `dbt build` in the project root first.")
        return

    leads = load_leads()
    leads["lead_month"] = pd.to_datetime(leads["lead_month"])

    with st.sidebar:
        page = st.radio("View", ["Management", "Decisions", "Reporting model"])
        st.divider()

    if page == "Management":
        management_view(leads)
    elif page == "Decisions":
        decisions_view(leads)
    else:
        reporting_table_view()


main()
