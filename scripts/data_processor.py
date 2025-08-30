import pandas as pd
import numpy as np
import holidays
import glob
import time
import sys
from pathlib import Path
from collections import defaultdict
import re

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

# us holidays from 2019 to 2025
US_HOLIDAYS_2019_2025 = holidays.US(
    state="CA", years=[2019, 2020, 2021, 2022, 2023, 2024, 2025]
)


def get_year_month_status():
    """
    check every year's processed month status
    return format: {
        '2019': {
            'processed_months': ['January', 'February', ...],
            'missing_months': ['August', 'September', ...],
            'file_path': Path to parquet file or None
        }
    }
    """
    year_status = {}
    processed_files = list(PROCESSED_DATA_DIR.glob("*_station_hour_processed.parquet"))

    # all possible months
    all_months = [
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

    for file_path in processed_files:
        try:
            # extract year from file name
            year = file_path.stem.split("_")[0]

            # read file to check included months
            df = pd.read_parquet(file_path)
            if "month" in df.columns:
                processed_months = sorted(df["month"].unique())
                missing_months = [
                    month for month in all_months if month not in processed_months
                ]

                year_status[year] = {
                    "processed_months": processed_months,
                    "missing_months": missing_months,
                    "file_path": file_path,
                }

                print(f"year {year}:")
                print(f"  processed months: {processed_months}")
                print(f"  missing months: {missing_months}")

        except Exception as e:
            print(f"error reading processed file {file_path}: {e}")

    return year_status


def get_available_raw_files():
    """
    return all available raw files, grouped by year and month
    return format: {
        '2019': {
            'January': 'path/to/file',
            'February': 'path/to/file',
            ...
        }
    }
    """
    raw_files = sorted(
        glob.glob(str(RAW_DATA_DIR / "*.txt")) + glob.glob(str(RAW_DATA_DIR / "*.gz"))
    )

    files_by_year_month = defaultdict(dict)

    for raw_file in raw_files:
        filename = Path(raw_file).name
        year, month = extract_year_month_from_filename(filename)

        if year and month:
            files_by_year_month[year][month] = raw_file

    return files_by_year_month


def extract_year_month_from_filename(filename):
    """
    extract year and month from raw file name
    """
    pattern = r"(\d{4})_(\d{2})"
    match = re.search(pattern, filename)

    if match:
        year = match.group(1)
        month_num = int(match.group(2))

        month_names = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December",
        }
        month_name = month_names.get(month_num)

        return year, month_name

    return None, None


def determine_files_to_process():
    """
    determine which files to process
    return format: {
        '2019': ['January', 'February'],  # months to process
        '2020': ['August', 'September']
    }
    """
    year_status = get_year_month_status()
    available_files = get_available_raw_files()

    files_to_process = defaultdict(list)

    # check each year
    for year, available_months in available_files.items():
        if year in year_status:
            # year has processed files
            missing_months = year_status[year]["missing_months"]

            # check if there are raw files to process
            for month in missing_months:
                if month in available_months:
                    files_to_process[year].append(month)

            if files_to_process[year]:
                print(f"year {year} needs to be processed: {files_to_process[year]}")
            else:
                print(f"year {year} is fully processed, skip")

        else:
            # year is not processed
            files_to_process[year] = list(available_months.keys())
            print(f"year {year} needs to be processed: {files_to_process[year]}")

    return files_to_process, available_files


def process_single_month_file(raw_file_path, meta_df):
    """process single month file"""
    try:
        print(f"processing file: {Path(raw_file_path).name}")

        raw_df = consume_raw(raw_file_path)
        if raw_df.empty:
            print(f"file is empty, skip: {Path(raw_file_path).name}")
            return None

        clean_df = clean_raw(raw_df, MIN_PCT_OBS, US_HOLIDAYS_2019_2025)
        if clean_df.empty:
            print(f"after cleaning, no data, skip: {Path(raw_file_path).name}")
            return None

        summarized_df = sum_for_hours_by_month(clean_df)
        if summarized_df.empty:
            print(f"after summarizing, no data, skip: {Path(raw_file_path).name}")
            return None

        merged_df = merge_with_meta(summarized_df, meta_df)
        return merged_df

    except Exception as e:
        print(f"error processing file {raw_file_path}: {e}")
        return None


def update_yearly_file(new_monthly_data, year, existing_file_path=None):
    """
    update yearly file: merge new data to existing file or create new file
    """
    if new_monthly_data is None or new_monthly_data.empty:
        return

    year_file = PROCESSED_DATA_DIR / f"{year}_station_hour_processed.parquet"

    try:
        if existing_file_path and existing_file_path.exists():
            # read existing data
            existing_df = pd.read_parquet(existing_file_path)
            print(f"existing file contains {len(existing_df):,} records")

            # merge new data
            combined_df = pd.concat([existing_df, new_monthly_data], ignore_index=True)
            print(f"added {len(new_monthly_data):,} records")
        else:
            # create new file
            combined_df = new_monthly_data
            print(
                f"created new yearly file, contains {len(new_monthly_data):,} records"
            )

        # save file
        combined_df.to_parquet(year_file, index=False)
        print(f"saved to: {year_file}")
        print(f"total {len(combined_df):,} records")

    except Exception as e:
        print(f"error saving yearly file: {e}")


def consume_raw(raw_file_path):
    try:
        # Normalize to Path for cross-platform handling
        p = Path(raw_file_path)

        # check if file is compressed
        if p.suffix == ".gz":
            import gzip

            with gzip.open(p, "rt") as f:
                df = pd.read_csv(f, sep=",", header=None, names=RAW_HOURLY_COLS)
        else:
            df = pd.read_csv(p, sep=",", header=None, names=RAW_HOURLY_COLS)

        print(f"Successfully read {p}, {len(df):,} rows")
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

    # ensure the final_cols are all in the df.columns
    cols_to_select = [col for col in FINAL_COLS if col in df.columns]

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
    """
    main function to process data
    """
    print("=== start processing ===")

    # check meta file
    meta_file = META_DATA_DIR / "d12_meta_20180918_20250713.csv"
    if not meta_file.exists():
        print(f"meta file does not exist: {meta_file}")
        return

    meta_df = pd.read_csv(meta_file)
    print(f"loaded meta data, contains {len(meta_df):,} stations\n")

    # determine which files to process
    files_to_process, available_files = determine_files_to_process()

    if not files_to_process:
        print("all available data are processed")
        return

    # get year status (to check if there is existing file)
    year_status = get_year_month_status()

    # process each year
    for year, months_to_process in files_to_process.items():
        print(f"\n--- processing {year} ---")
        print(f"months to process: {months_to_process}")

        year_monthly_data = []

        # process each month
        for month in months_to_process:
            raw_file_path = available_files[year][month]
            monthly_df = process_single_month_file(raw_file_path, meta_df)

            if monthly_df is not None and not monthly_df.empty:
                year_monthly_data.append(monthly_df)

        # merge all new processed data
        if year_monthly_data:
            combined_new_data = pd.concat(year_monthly_data, ignore_index=True)

            # get existing file path (if exists)
            existing_file_path = year_status.get(year, {}).get("file_path", None)

            # update yearly file
            update_yearly_file(combined_new_data, year, existing_file_path)
        else:
            print(f"{year} has no successfully processed data")


if __name__ == "__main__":
    start_time = time.time()
    main()
    end_time = time.time()
    print(f"Time taken: {end_time - start_time} seconds")
