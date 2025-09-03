#!/usr/bin/env python3
"""
Streamlit Dashboard for CalTrans PeMS ETL

- Reads yearly Parquet files from data/processed/
- Provides simple filters and KPIs
- Visualizes speed/flow/occupancy by hour and month

Run:
    streamlit run scripts/dashboard.py --server.address 0.0.0.0 --server.port 8501
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
    st.sidebar.header("Filters")
    # Year filter
    years = (
        sorted(df["year"].dropna().astype(int).unique().tolist())
        if not df.empty
        else []
    )
    year_sel = st.sidebar.multiselect("Year", years, default=years)

    # Route filter
    routes_numeric = df["route"].dropna().unique() if not df.empty else []
    routes_sorted = sorted(routes_numeric, key=lambda x: float(x) if pd.notna(x) else 0)
    routes = [str(route) for route in routes_sorted]
    route_sel = st.sidebar.multiselect("Route", routes, default=routes[:10])

    # Direction filter
    dirs = (
        sorted(pd.Series(df["direction"].dropna().unique()).astype(str))
        if not df.empty
        else []
    )
    dir_sel = st.sidebar.multiselect("Direction", dirs, default=dirs)

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
        if not df.empty
        else []
    )
    month_sel = st.sidebar.multiselect("Month", months_avail, default=months_avail)

    # Hour filter
    hours = (
        sorted(pd.Series(df["hour"].dropna().unique()).astype(int))
        if not df.empty
        else list(range(0, 24))
    )
    hour_min, hour_max = (min(hours) if hours else 0, max(hours) if hours else 23)
    hour_rng = st.sidebar.slider(
        "Hour range", min_value=0, max_value=23, value=(hour_min, hour_max)
    )

    mask = pd.Series(True, index=df.index)
    if year_sel:
        mask &= df["year"].isin(year_sel)
    if route_sel:
        mask &= df["route"].astype(str).isin(route_sel)
    if dir_sel:
        mask &= df["direction"].astype(str).isin(dir_sel)
    if month_sel:
        mask &= df["month"].isin(month_sel)
    mask &= df["hour"].between(hour_rng[0], hour_rng[1])

    return df[mask].copy()


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
    # plot 1: Speed by Hour
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

    # plot 2: Flow by Month
    st.subheader("Flow by Month")
    cat_months = pd.Categorical(
        df["month"],
        categories=[
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
        ],
        ordered=True,
    )
    by_month_year = (
        df.assign(month_cat=cat_months)
        .dropna(subset=["month_cat", "avg_flow"])
        .groupby(["month_cat", "year"])["avg_flow"]
        .mean()
        .reset_index()
        .rename(columns={"month_cat": "month"})
    )

    # create pivot table
    years = sorted(by_month_year["year"].unique())
    months = by_month_year["month"].unique()
    fig = go.Figure()
    for year in years:
        year_data = by_month_year[by_month_year["year"] == year]
        fig.add_trace(
            go.Bar(
                x=year_data["month"],
                y=year_data["avg_flow"],
                name=str(year),
            )
        )

    fig.update_layout(
        barmode="group",
        xaxis_title="Month",
        yaxis_title="Average Flow",
        title="Average Flow by Month and Year",
        legend_title="Year",
    )

    st.plotly_chart(fig)
    # st.bar_chart(flow_pivot)

    # Optional map if lat/lon exists
    if {"latitude", "longitude"}.issubset(df.columns):
        locs = df.dropna(subset=["latitude", "longitude"])[
            ["latitude", "longitude"]
        ].drop_duplicates()
        if not locs.empty:
            st.subheader("Stations Map")
            st.map(locs.rename(columns={"latitude": "lat", "longitude": "lon"}))


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
