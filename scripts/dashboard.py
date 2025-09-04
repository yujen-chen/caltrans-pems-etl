#!/usr/bin/env python3
"""
Streamlit Dashboard for CalTrans PeMS ETL

- Reads yearly Parquet files from data/processed/
- Provides simple filters and KPIs
- Visualizes speed/flow/occupancy by hour and month

Run:
    streamlit run scripts/dashboard.py --server.address 0.0.0.0 --server.port 8501
"""

"""
TODO:
- [ ] Add ML and HV filters
- [ ] Update the bar chart title

"""

import os
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import streamlit as st

import plotly.graph_objects as go

# Ensure project root is on sys.path (so `config` can be imported)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import PROCESSED_DATA_DIR

# Consistent color palette for years (bars and lines)
# Tableau 10 color palette
YEAR_COLOR_PALETTE = [
    "#4E79A7",  # blue
    "#F28E2B",  # orange
    "#E15759",  # red
    "#76B7B2",  # teal
    "#59A14F",  # green
    "#EDC948",  # yellow
    "#B07AA1",  # purple
    "#FF9DA7",  # pink
    "#9C755F",  # brown
    "#BAB0AC",  # gray
]


@st.cache_data(ttl=600)
def load_year_file(fp: Path) -> pd.DataFrame:
    df = pd.read_parquet(fp)
    # Add year from filename if missing
    try:
        year = int(fp.stem.split("_")[0])
        if "year" not in df.columns:
            df["year"] = year
    except Exception:
        pass
    return df


@st.cache_data(ttl=600)
def load_all_processed() -> pd.DataFrame:
    files: List[Path] = sorted(
        PROCESSED_DATA_DIR.glob("*_station_hour_processed.parquet")
    )
    if not files:
        return pd.DataFrame()
    dfs = []
    for fp in files:
        try:
            dfs.append(load_year_file(fp))
        except Exception:
            continue
    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    # Ensure expected columns exist gracefully
    expected = [
        "station",
        "district",
        "route",
        "direction",
        "type",
        "hour",
        "month",
        "lanes",
        "length",
        "median_flow",
        "avg_flow",
        "sd_flow",
        "median_speed",
        "avg_speed",
        "sd_speed",
        "median_occup",
        "avg_occup",
        "sd_occup",
        "year",
        "latitude",
        "longitude",
    ]
    for col in expected:
        if col not in df.columns:
            # fill missing numeric with NaN, others with None
            df[col] = (
                np.nan
                if col not in ("station", "route", "direction", "type", "month")
                else None
            )
    return df


def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filters with state model S0–S2:
    - S0: 未選路線 -> 僅一般篩選（年/月/時），提示選擇路線。
    - S1: 單一路線 -> 啟用依 abs_pm 的區段選擇與站點多選。
    - S2: 2–3 路線 -> 為每條路線各自提供區段/站點設定，合併過濾（Union）。
    保持圖表與地圖型別不變。
    """

    st.sidebar.header("Filters")

    # Year filter
    years = (
        sorted(df["year"].dropna().astype(int).unique().tolist())
        if not df.empty and "year" in df.columns
        else []
    )
    year_sel = st.sidebar.multiselect("Year", years, default=years)

    # Month filter
    months_order = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    months_avail = (
        [m for m in months_order if m in set(df["month"].dropna().unique())]
        if (not df.empty and "month" in df.columns)
        else []
    )
    month_sel = st.sidebar.multiselect("Month", months_avail, default=months_avail)

    # Hour filter
    hours = (
        sorted(pd.Series(df["hour"].dropna().unique()).astype(int))
        if (not df.empty and "hour" in df.columns)
        else list(range(0, 24))
    )
    hour_min, hour_max = (min(hours) if hours else 0, max(hours) if hours else 23)
    hour_rng = st.sidebar.slider(
        "Hour range", min_value=0, max_value=23, value=(hour_min, hour_max)
    )

    # Route options
    routes_numeric = (
        df["route"].dropna().unique()
        if (not df.empty and "route" in df.columns)
        else []
    )
    routes_sorted = sorted(routes_numeric, key=lambda x: float(x) if pd.notna(x) else 0)
    routes = [str(route) for route in routes_sorted]

    # Route selection（最多 3 條）
    route_sel = st.sidebar.multiselect(
        "Route (max 3)", routes, default=routes[:1], key="route_sel"
    )
    if len(route_sel) > 3:
        st.sidebar.warning("已選超過 3 條路線，僅套用前 3 條。")
    route_sel_eff = route_sel[:3]

    # Switch between: Bars + Lines / Bars only / Lines only
    st.sidebar.markdown("---")
    st.sidebar.radio(
        "Display",
        options=["Bars + Lines", "Bars only", "Lines only"],
        index=0,
        key="display_mode",
        help="Choose whether to show both bars and lines, bars only, or lines only.",
    )

    # Keep chart simple: no bar statistic or line smoothing switch

    # Common conditions: year/month/hour
    base_mask = pd.Series(True, index=df.index)
    if year_sel:
        base_mask &= df["year"].isin(year_sel)
    if month_sel:
        base_mask &= df["month"].isin(month_sel)
    base_mask &= df["hour"].between(hour_rng[0], hour_rng[1])

    # If no route selected (S0)
    if not route_sel_eff:
        st.sidebar.info("請從 Route 中選擇最多 3 條以開始（S0）。")
        return df[base_mask].copy()

    has_abs_pm = ("abs_pm" in df.columns) and (df["abs_pm"].notna().any())

    # S1: single route; S2: 2–3 routes
    route_union_mask = pd.Series(False, index=df.index)

    for r in route_sel_eff:
        # After applying base_mask, calculate the actual available directions for that route
        df_base = df[base_mask]
        df_r = df_base[df_base["route"].astype(str) == str(r)]

        # Direction selection for each route (only show available directions for that route)
        expander = st.sidebar.expander(f"Route {r}")
        with expander:
            if df_r.empty:
                st.caption(
                    "No data available for this route under current year/month/hour combination."
                )
                continue

            if "direction" in df.columns:
                dir_options_r = sorted(
                    df_r["direction"].dropna().astype(str).unique().tolist()
                )
            else:
                dir_options_r = []

            if dir_options_r:
                dir_choices_r = st.multiselect(
                    "Direction（Multiple Selection Available）",
                    options=dir_options_r,
                    default=dir_options_r,
                    key=f"dir_{r}",
                )
            else:
                dir_choices_r = []
                st.caption(
                    "This route has no available directions or missing direction column."
                )

            # route+direction mask (if no direction column, only filter by route)
            if dir_options_r and "direction" in df.columns:
                if dir_choices_r:
                    rd_mask = (df["route"].astype(str) == str(r)) & (
                        df["direction"]
                        .astype(str)
                        .isin([str(d) for d in dir_choices_r])
                    )
                else:
                    st.caption("No direction selected, this route will be ignored.")
                    continue
            else:
                rd_mask = df["route"].astype(str) == str(r)

            df_rd = df[rd_mask & base_mask]
            if df_rd.empty:
                st.caption("No data available for this route/direction combination.")
                continue

            station_series = df_rd["station"].dropna().astype(str).unique()
            # Sort: if abs_pm exists, sort by abs_pm in ascending order; otherwise, sort by station string
            if has_abs_pm:
                tmp = df_rd.dropna(subset=["station", "abs_pm"])[
                    ["station", "abs_pm"]
                ].drop_duplicates()
                tmp["station"] = tmp["station"].astype(str)
                tmp = tmp.sort_values("abs_pm", kind="mergesort")
                station_sorted = tmp["station"].tolist()
            else:
                station_sorted = sorted(station_series.tolist())

            # abs_pm segment selection (if available)
            selected_station_ids: List[str]
            if has_abs_pm and not df_rd["abs_pm"].dropna().empty:
                abs_min = float(np.nanmin(df_rd["abs_pm"].values))
                abs_max = float(np.nanmax(df_rd["abs_pm"].values))
                # Default to global at both ends; step is 0.1 mile
                abs_rng = st.slider(
                    f"abs_pm 範圍（{r}）",
                    min_value=float(np.floor(abs_min)),
                    max_value=float(np.ceil(abs_max)),
                    value=(float(np.floor(abs_min)), float(np.ceil(abs_max))),
                    step=0.1,
                    key=f"abs_rng_{r}",
                )
                # Select stations within the range
                in_range = df_rd.dropna(subset=["station", "abs_pm"]).query(
                    "@abs_rng[0] <= abs_pm <= @abs_rng[1]"
                )
                in_range_ids = (
                    in_range["station"].astype(str).dropna().unique().tolist()
                )
                # Station list multiple selection (default to all within range)
                selected_station_ids = st.multiselect(
                    f"站點多選（{r}）",
                    options=[s for s in station_sorted if s in set(in_range_ids)],
                    default=in_range_ids,
                    key=f"st_sel_{r}",
                )
                st.caption(
                    f"Selected {len(selected_station_ids)} stations (within abs_pm)"
                )
            else:
                st.info("無 abs_pm 欄位或資料為空，改以 station 清單選擇。")
                selected_station_ids = st.multiselect(
                    f"Station Multiple Selection ({r})",
                    options=station_sorted,
                    default=station_sorted,
                    key=f"st_sel_{r}",
                )

            # 本路線的站點遮罩
            if selected_station_ids:
                rd_station_mask = df["station"].astype(str).isin(selected_station_ids)
            else:
                # 若沒選到（例如範圍過窄），避免全排除：只套用 route+direction
                rd_station_mask = pd.Series(True, index=df.index)

            route_union_mask |= rd_mask & rd_station_mask

    # 最終遮罩
    final_mask = base_mask & route_union_mask
    return df[final_mask].copy()


def render_kpis(df: pd.DataFrame) -> None:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Records", f"{len(df):,}")
    with c2:
        stations = df["station"].nunique() if "station" in df.columns else 0
        st.metric("Stations", f"{stations:,}")
    with c3:
        avg_speed = df["avg_speed"].astype(float).mean()
        st.metric("Avg Speed", f"{avg_speed:0.1f} mph" if pd.notna(avg_speed) else "-")
    with c4:
        avg_flow = df["avg_flow"].astype(float).mean()
        st.metric("Avg Flow", f"{avg_flow:0.1f}" if pd.notna(avg_flow) else "-")


def render_charts(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No data available for current filters.")
        return

    # Optional map if lat/lon exists
    if {"latitude", "longitude"}.issubset(df.columns):
        locs = df.dropna(subset=["latitude", "longitude"])[
            ["latitude", "longitude"]
        ].drop_duplicates()
        if not locs.empty:
            st.subheader("Stations Map")
            st.map(locs.rename(columns={"latitude": "lat", "longitude": "lon"}))

    # plot 1: Flow by Month (per selected route; vertical stack up to 3)
    st.subheader("Flow by Month")
    month_order = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    selected_routes = st.session_state.get("route_sel", [])
    # 建立年度配色對應（在目前篩選資料範圍內全域一致）
    year_color_map = {}
    if "year" in df.columns:
        years_vals = pd.Series(df["year"].dropna()).tolist()
        try:
            years_vals = [int(y) for y in years_vals]
        except Exception:
            years_vals = pd.Series(years_vals).astype(int).tolist()
        years_unique = sorted(set(years_vals))
        for i, y in enumerate(years_unique):
            year_color_map[int(y)] = YEAR_COLOR_PALETTE[i % len(YEAR_COLOR_PALETTE)]
    route_list = (
        selected_routes[:3]
        if selected_routes
        else sorted(df["route"].astype(str).dropna().unique().tolist())[:1]
    )

    if not route_list:
        st.info("No route selected for monthly flow chart.")
    for r in route_list:
        df_r = df[df["route"].astype(str) == str(r)]
        if df_r.empty:
            st.caption(f"Route {r}: no data under current filters.")
            continue

        df_r = df_r.copy()
        # Prepare per-lane flow for line (right axis)
        if "lanes" in df_r.columns:
            flo = df_r["avg_flow"].astype(float)
            lns = df_r["lanes"].astype(float)
            with np.errstate(divide="ignore", invalid="ignore"):
                df_r["flow_per_lane"] = np.where(lns > 0, flo / lns, np.nan)
        else:
            df_r["flow_per_lane"] = np.nan

        cat_months = pd.Categorical(df_r["month"], categories=month_order, ordered=True)

        # Bars: average flow (veh/h) per month-year across selected stations
        bars_by_month_year = (
            df_r.assign(month_cat=cat_months)
            .dropna(subset=["month_cat", "avg_flow", "year"])
            .groupby(["month_cat", "year"])["avg_flow"]
            .mean()
            .reset_index()
            .rename(columns={"month_cat": "month", "avg_flow": "bar_value"})
        )
        bar_y_title = "Average Flow (veh/h)"
        if bars_by_month_year.empty:
            st.caption(f"Route {r}: insufficient data to plot.")
            continue

        # Line (right axis): per-year monthly medians
        use_per_lane_line = df_r["flow_per_lane"].notna().any()
        y2_title = (
            "Median Flow per Lane (veh/h/ln)"
            if use_per_lane_line
            else "Median Flow (veh/h)"
        )

        years = sorted(bars_by_month_year["year"].unique())
        fig = go.Figure()
        bars_enabled = st.session_state.get("display_mode", "Bars + Lines") in (
            "Bars + Lines",
            "Bars only",
        )
        lines_enabled = st.session_state.get("display_mode", "Bars + Lines") in (
            "Bars + Lines",
            "Lines only",
        )
        if bars_enabled:
            for year in years:
                year_data = bars_by_month_year[bars_by_month_year["year"] == year]
                try:
                    y_int = int(year)
                except Exception:
                    y_int = None
                color = year_color_map.get(y_int) if y_int is not None else None
                fig.add_trace(
                    go.Bar(
                        x=year_data["month"],
                        y=year_data["bar_value"],
                        name=f"{year} Avg. Flow",
                        marker_color=color,
                        legendgroup=str(year),
                    )
                )

        # Add line traces on secondary (right) axis, one per year
        if lines_enabled:
            for year in years:
                df_y = df_r[df_r["year"] == year].copy()
                try:
                    y_int = int(year)
                except Exception:
                    y_int = None
                color = year_color_map.get(y_int) if y_int is not None else None
                df_y["month_cat"] = pd.Categorical(
                    df_y["month"], categories=month_order, ordered=True
                )
                if use_per_lane_line:
                    line_df = (
                        df_y.dropna(
                            subset=["month_cat", "flow_per_lane"]
                        )  # per-lane available
                        .groupby(["month_cat"])["flow_per_lane"]
                        .median()
                        .reset_index()
                        .rename(
                            columns={
                                "month_cat": "month",
                                "flow_per_lane": "line_value",
                            }
                        )
                    )
                    line_name = f"Median per-lane ({year})"
                else:
                    line_df = (
                        df_y.dropna(subset=["month_cat", "avg_flow"])  # fallback
                        .groupby(["month_cat"])["avg_flow"]
                        .median()
                        .reset_index()
                        .rename(
                            columns={"month_cat": "month", "avg_flow": "line_value"}
                        )
                    )
                    line_name = f"Median flow ({year})"

                if not line_df.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=line_df["month"],
                            y=line_df["line_value"],
                            name=line_name,
                            mode="lines+markers",
                            yaxis="y2",
                            line=dict(color=color),
                            marker=dict(color=color),
                            legendgroup=str(year),
                        )
                    )

        # Dynamic title description: (Bars only / Lines only / Bars + Lines)
        mode_label = st.session_state.get("display_mode", "Bars + Lines")
        line_label = (
            "Median per-lane by year" if use_per_lane_line else "Median flow by year"
        )
        if mode_label == "Bars only":
            title_txt = f"Route {r} – Monthly Flow (Bars=Avg)"
        elif mode_label == "Lines only":
            title_txt = f"Route {r} – Monthly Flow (Line={line_label})"
        else:
            title_txt = f"Route {r} – Monthly Flow (Bars=Avg, Line={line_label})"

        fig.update_layout(
            barmode="group",
            xaxis_title="Month",
            yaxis=dict(title=bar_y_title),
            yaxis2=dict(title=y2_title, overlaying="y", side="right", showgrid=False),
            title=title_txt,
            legend_title="Legend",
            legend=dict(
                orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5
            ),
        )

        st.plotly_chart(fig)
    # st.bar_chart(flow_pivot)

    # plot 2: Speed by Hour
    st.subheader("Speed by Hour")
    by_hour = (
        df.dropna(subset=["hour", "avg_speed"])
        .groupby(["hour", "year"])["avg_speed"]
        .mean()
        .reset_index()
    )

    # pivot to get year as columns
    speed_pivot = by_hour.pivot(index="hour", columns="year", values="avg_speed")

    st.line_chart(speed_pivot)


def render_download(df: pd.DataFrame) -> None:
    if df.empty:
        return
    st.subheader("Download")
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download filtered CSV",
        data=csv,
        file_name="pems_filtered.csv",
        mime="text/csv",
    )


def main():
    st.set_page_config(page_title="CalTrans PeMS Dashboard", layout="wide")
    st.title("CalTrans PeMS – Station Hour Dashboard")
    st.caption("Data source: CalTrans PeMS (District 12 by default)")

    df = load_all_processed()
    if df.empty:
        st.warning(
            "No processed data found. Place yearly Parquet files under data/processed/."
        )
        st.stop()

    fdf = sidebar_filters(df)
    render_kpis(fdf)
    render_charts(fdf)
    render_download(fdf)


if __name__ == "__main__":
    main()
