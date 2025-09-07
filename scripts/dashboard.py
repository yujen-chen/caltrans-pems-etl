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

    # Route selection（最多 3 條；預設不選）
    route_options = routes
    route_sel = st.sidebar.multiselect(
        "Route (max 3)", route_options, default=[], key="route_sel"
    )
    all_routes = False
    if len(route_sel) > 3:
        st.sidebar.warning("已選超過 3 條路線，僅套用前 3 條。")
    # 最多取前三條
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

    # 只保留「每路線」Lane Type；不提供全域 Lane Type（避免全路線匯總誤解）
    type_col_exists = "type" in df.columns

    # 未選路線（S0）：提示並避免回傳全路線資料以免誤解
    if not route_sel_eff:
        st.sidebar.info("請從 Route 中選擇 1–3 條以開始（S0）。")
        return df.iloc[0:0].copy()

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

            # Lane Type（每路線）：在 base_mask + route 條件下的可用型態
            selected_type_r = None
            if type_col_exists:
                types_avail_r = (
                    df_r["type"].dropna().astype(str).str.upper().unique().tolist()
                )
                # 僅顯示 ML/HV 的交集，若資料有其他值則附加其餘
                ordered = [t for t in ["ML", "HV"] if t in set(types_avail_r)]
                extras = [t for t in types_avail_r if t not in set(["ML", "HV"])]
                opts_r = ordered + extras
                if not opts_r:
                    st.caption("No lane type info for this route; 將不套用型態篩選。")
                else:
                    default_idx = 0
                    if "ML" in opts_r:
                        default_idx = opts_r.index("ML")
                    selected_type_r = st.radio(
                        "Lane Type",
                        options=opts_r,
                        index=default_idx,
                        key=f"lane_type_{r}",
                        help="選擇此路線的車道型態（ML=Main Lane, HV=HOV Lane）",
                    )
                    if "HV" not in set(types_avail_r):
                        st.caption("HV（HOV）在此路線目前條件下無資料")

            # 初始 route 遮罩（含型態）
            if selected_type_r and type_col_exists:
                rd_mask = (df["route"].astype(str) == str(r)) & (
                    df["type"].astype(str).str.upper() == selected_type_r
                )
                df_r = df[rd_mask & base_mask]
                if df_r.empty:
                    st.caption("No data for selected lane type under this route.")
                    continue
            else:
                rd_mask = df["route"].astype(str) == str(r)

            # Direction 選擇：單選 North/South 或 East/West，並提供 Two‑way（sum）
            # 先偵測可用方向，使用第一個字母（N/S/E/W）做正規化
            dir_options_r = []
            if "direction" in df.columns:
                dir_options_r = (
                    df_r["direction"].dropna().astype(str).str.upper().str[0].unique().tolist()
                )
            dir_set = set(dir_options_r)

            # 判斷此路線的方向型態與 radio 選項
            if ("N" in dir_set) or ("S" in dir_set):
                dir_radio_opts = ["North", "South", "Two-way (sum)"]
                default_idx = 0  # 預設 North
                dir_mode = st.radio(
                    "Direction",
                    options=dir_radio_opts,
                    index=default_idx,
                    key=f"dir_mode_{r}",
                    help="選擇方向；Two-way（sum）為雙向平均流量的加總（單向缺資料則退化為單向）",
                )
                # 依選擇建立遮罩：Two‑way 不限制方向；單向以首字母比對（N 或 S）
                if dir_mode == "North":
                    rd_mask = df["route"].astype(str) == str(r)
                    rd_mask &= df["direction"].astype(str).str.upper().str[0] == "N"
                elif dir_mode == "South":
                    rd_mask = df["route"].astype(str) == str(r)
                    rd_mask &= df["direction"].astype(str).str.upper().str[0] == "S"
                else:
                    rd_mask = df["route"].astype(str) == str(r)
                if selected_type_r and type_col_exists:
                    rd_mask &= df["type"].astype(str).str.upper() == selected_type_r
            elif ("E" in dir_set) or ("W" in dir_set):
                dir_radio_opts = ["East", "West", "Two-way (sum)"]
                default_idx = 0  # 預設 East
                dir_mode = st.radio(
                    "Direction",
                    options=dir_radio_opts,
                    index=default_idx,
                    key=f"dir_mode_{r}",
                    help="選擇方向；Two-way（sum）為雙向平均流量的加總（單向缺資料則退化為單向）",
                )
                if dir_mode == "East":
                    rd_mask = df["route"].astype(str) == str(r)
                    rd_mask &= df["direction"].astype(str).str.upper().str[0] == "E"
                elif dir_mode == "West":
                    rd_mask = df["route"].astype(str) == str(r)
                    rd_mask &= df["direction"].astype(str).str.upper().str[0] == "W"
                else:
                    rd_mask = df["route"].astype(str) == str(r)
                if selected_type_r and type_col_exists:
                    rd_mask &= df["type"].astype(str).str.upper() == selected_type_r
            else:
                # 無 direction 欄位或皆為缺失：僅以 route/type 過濾
                st.caption(
                    "This route has no standard N/S/E/W direction values or missing direction column."
                )
                rd_mask = df["route"].astype(str) == str(r)
                if selected_type_r and type_col_exists:
                    rd_mask &= df["type"].astype(str).str.upper() == selected_type_r

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


def _render_flow_by_month_for_route(df: pd.DataFrame, r: str, month_order: list, year_color_map: dict) -> None:
    df_r = df[df["route"].astype(str) == str(r)]
    if df_r.empty:
        st.caption(f"Route {r}: no data under current filters.")
        return

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

    # 方向模式（單向或 Two‑way（sum））：從 session 取得
    dir_mode = st.session_state.get(f"dir_mode_{r}")

    # Bars：
    # - 單向：在目前資料（已由 sidebar 過濾為單向）上取平均
    # - Two‑way（sum）：先算每方向的月別平均，再將兩個相反方向相加（單向缺資料則退化為單向）
    if isinstance(dir_mode, str) and "Two-way" in dir_mode:
        df_tmp = df_r.copy()
        df_tmp["dir_letter"] = df_tmp["direction"].astype(str).str.upper().str[0]
        # 判斷使用 N/S 或 E/W 組合
        letters = set(df_tmp["dir_letter"].dropna().unique().tolist())
        if ("N" in letters) or ("S" in letters):
            pair = ("N", "S")
        else:
            pair = ("E", "W")

        by_dir = (
            df_tmp.assign(month_cat=cat_months)
            .dropna(subset=["month_cat", "avg_flow", "year"])
            .groupby(["month_cat", "year", "dir_letter"])["avg_flow"]
            .mean()
            .reset_index()
        )
        piv = by_dir.pivot(index=["month_cat", "year"], columns="dir_letter", values="avg_flow").reset_index()
        for d in pair:
            if d not in piv.columns:
                piv[d] = np.nan
        piv["bar_value"] = piv[list(pair)].sum(axis=1, skipna=True)
        bars_by_month_year = piv.rename(columns={"month_cat": "month"})[["month", "year", "bar_value"]]
    else:
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
        return

    # Line (right axis): per-year monthly medians
    use_per_lane_line = df_r["flow_per_lane"].notna().any()
    y2_title = (
        "Median Flow per Lane (veh/h/ln)" if use_per_lane_line else "Median Flow (veh/h)"
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
                    df_y.dropna(subset=["month_cat", "flow_per_lane"])  # per-lane available
                    .groupby(["month_cat"])["flow_per_lane"]
                    .median()
                    .reset_index()
                    .rename(columns={"month_cat": "month", "flow_per_lane": "line_value"})
                )
                line_name = f"Median per-lane ({year})"
            else:
                line_df = (
                    df_y.dropna(subset=["month_cat", "avg_flow"])  # fallback
                    .groupby(["month_cat"])["avg_flow"]
                    .median()
                    .reset_index()
                    .rename(columns={"month_cat": "month", "avg_flow": "line_value"})
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
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
    )

    st.plotly_chart(fig)

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
    route_list = selected_routes[:3] if selected_routes else []
    if not route_list:
        st.info("請先於左側選擇 1–3 條路線以顯示月別流量圖。")
        return
    for r in route_list:
        _render_flow_by_month_for_route(df, r, month_order, year_color_map)
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
