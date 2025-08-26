import pandas as pd
import numpy as np
import holidays
import glob
import time
import sys
from pathlib import Path


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import (
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    META_DATA_DIR,
    MIN_PCT_OBS,
    RAW_HOURLY_COLS,
    FINAL_COLS,
)


# SETTINGS

# num of cols = 42
RAW_HOURLY_COLS = [
    "time_stamp_string",
    "station",
    "district",
    "route",
    "direction",
    "type",
    "length",
    "samples",
    "pct_obs",
    "flow",
    "occupancy",
    "speed",
    "delay_35",
    "delay_40",
    "delay_45",
    "delay_50",
    "delay_55",
    "delay_60",
    "flow_1",
    "occ_1",
    "speed_1",
    "flow_2",
    "occ_2",
    "speed_2",
    "flow_3",
    "occ_3",
    "speed_3",
    "flow_4",
    "occ_4",
    "speed_4",
    "flow_5",
    "occ_5",
    "speed_5",
    "flow_6",
    "occ_6",
    "speed_6",
    "flow_7",
    "occ_7",
    "speed_7",
    "flow_8",
    "occ_8",
    "speed_8",
]

# set min pct obs
MIN_PCT_OBS = 80

# us holidays from 2019 to 2025
US_HOLIDAYS_2019_2025 = holidays.US(
    state="CA", years=[2019, 2020, 2021, 2022, 2023, 2024, 2025]
)


def consume_raw(raw_file_path):
    try:
        # check if file is compressed
        if raw_file_path.endswith(".gz"):
            import gzip

            with gzip.open(raw_file_path, "rt") as f:
                df = pd.read_csv(f, sep=",", header=None, names=RAW_HOURLY_COLS)
        else:
            df = pd.read_csv(raw_file_path, sep=",", header=None, names=RAW_HOURLY_COLS)

        print(f"Successfully read {raw_file_path}, {len(df):,} rows")
        return df

    except Exception as e:
        print(f"Failed to read {raw_file_path}: {e}")
        return pd.DataFrame()


# clean raw function
def clean_raw(raw_df, min_pct_obs, us_holidays):
    # read raw_df
    df = raw_df.copy()

    # filter rows based on 'pct_obs'
    df = df[df["pct_obs"] >= min_pct_obs]

    # convert timestamp to datetime obj
    datetime_col = pd.to_datetime(df["time_stamp_string"], format="%m/%d/%Y %H:%M:%S")

    # Create new date and time columns
    df["date"] = datetime_col.dt.date
    df["year"] = datetime_col.dt.year
    df["month"] = datetime_col.dt.month_name()
    df["hour"] = datetime_col.dt.hour
    df["day_of_week"] = datetime_col.dt.day_name()

    # keep Tuesday, Wednesday, and Thursday
    days_to_keep = ["Tuesday", "Wednesday", "Thursday"]
    df = df[df["day_of_week"].isin(days_to_keep)]

    # filter out holidays
    df = df[~df["date"].isin(us_holidays)]

    # create lanes col and determine number of lanes
    df["lanes"] = 8
    for i in range(7, 0, -1):
        df.loc[df[f"flow_{i}"].isna(), "lanes"] = i

    # Define the final list of columns to keep and reorder
    final_cols = [
        "date",
        "month",
        "day_of_week",
        "station",
        "district",
        "route",
        "direction",
        "type",
        "hour",
        "pct_obs",
        "length",
        "flow",
        "speed",
        "lanes",
        "occupancy",
    ]

    # ensure the final_cols are all in the df.columns
    cols_to_select = [col for col in final_cols if col in df.columns]

    df = df[cols_to_select]

    return df


# summarize the hourly data
def sum_for_hours_by_month(clean_district_station_hour_df):
    df = clean_district_station_hour_df.copy()
    grouping_cols = [
        "station",
        "district",
        "route",
        "direction",
        "type",
        "hour",
        "month",
        "lanes",
        "length",
    ]

    summary_df = (
        df.groupby(grouping_cols)
        .agg(
            median_flow=("flow", "median"),
            avg_flow=("flow", "mean"),
            sd_flow=("flow", "std"),
            median_speed=("speed", "median"),
            avg_speed=("speed", "mean"),
            sd_speed=("speed", "std"),
            median_occup=("occupancy", "median"),
            avg_occup=("occupancy", "mean"),
            sd_occup=("occupancy", "std"),
            days_observed=("flow", "size"),
        )
        .reset_index()
    )

    filtered_df = summary_df[summary_df["days_observed"] >= 4]

    return filtered_df


def merge_with_meta(summarized_df, meta_df):
    summarized_df = summarized_df.copy()
    meta_df = meta_df.copy()

    stations_matched = summarized_df["station"].isin(meta_df["station"]).all()

    if stations_matched:
        print("All stations matched, start merging")
        meta_df = meta_df[
            [
                "station",
                "route",
                "direction",
                "district",
                "county",
                "state_pm",
                "abs_pm",
                "latitude",
                "longitude",
            ]
        ]
        merged_df = pd.merge(
            summarized_df,
            meta_df,
            on=["station", "route", "direction", "district"],
            how="left",
        )
        return merged_df
    else:
        stations_missing = summarized_df[
            ~summarized_df["station"].isin(meta_df["station"])
        ]
        print("Not all stations exist.")
        print(stations_missing)


def main():

    all_processed_dfs = []

    # read in raw data
    raw_files = glob.glob(str(RAW_DATA_DIR / "*.txt")) + glob.glob(
        str(RAW_DATA_DIR / "*.gz")
    )
    meta_file = META_DATA_DIR / "d12_meta_20180918_20250713.csv"

    # check if raw files exist
    if not raw_files:
        print("No raw files found")
        return

    # check if meta file exists
    if not meta_file.exists():
        print(f"Meta file not found: {meta_file}")
        return

    meta_df = pd.read_csv(meta_file)

    for raw_file in raw_files:
        file_path = Path(raw_file)
        print(f"Processing: {file_path.name}")
        raw_df = consume_raw(file_path)

        if raw_df.empty:
            print(f"Skipping empty file: {file_path.name}")
            continue

        clean_df = clean_raw(raw_df, MIN_PCT_OBS, US_HOLIDAYS_2019_2025)
        summarized_df = sum_for_hours_by_month(clean_df)
        merged_df = merge_with_meta(summarized_df, meta_df)
        all_processed_dfs.append(merged_df)

    print(f"Processed {len(all_processed_dfs)} files")

    if all_processed_dfs:
        all_processed_df = pd.concat(all_processed_dfs)
        output_file = PROCESSED_DATA_DIR / "all_processed_df.csv"
        all_processed_df.to_csv(output_file, index=False)
        print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    start_time = time.time()
    main()
    end_time = time.time()
    print(f"Time taken: {end_time - start_time} seconds")
