# config/settings.py
import os
from pathlib import Path

# project root
PROJECT_ROOT = Path(__file__).parent.parent

# data paths
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
META_DATA_DIR = DATA_DIR / "meta"
EXPORTS_DATA_DIR = DATA_DIR / "exports"

# ensure directories exist
for dir_path in [RAW_DATA_DIR, PROCESSED_DATA_DIR, META_DATA_DIR, EXPORTS_DATA_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# processing parameters
MIN_PCT_OBS = 80
REQUIRED_DAYS_OBSERVED = 4

# PeMS settings
BASE_URL = "http://pems.dot.ca.gov"
CLEARING_HOUSE_URL = (
    "{}/?srq=clearinghouse&district_id={}&yy={}&type={}&returnformat=text"
)
DISTRICTS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]

# R2 Storage Configuration
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "pems-processed")
R2_UPLOAD_ENABLED = os.getenv("R2_UPLOAD_ENABLED", "false").lower() == "true"
R2_UPLOAD_RAW = os.getenv("R2_UPLOAD_RAW", "true").lower() == "true"
R2_RAW_ROLLING_MONTHS = int(os.getenv("R2_RAW_ROLLING_MONTHS", "12"))
R2_LOCAL_RAW_RETENTION_DAYS = int(os.getenv("R2_LOCAL_RAW_RETENTION_DAYS", "30"))

# data processing constants
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

FINAL_COLS = [
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

# DuckDB Configuration
DUCKDB_PATH = os.getenv("DUCKDB_PATH", ":memory:")
DUCKDB_CACHE_SIZE = int(os.getenv("DUCKDB_CACHE_SIZE", "100"))
DUCKDB_THREADS = int(os.getenv("DUCKDB_THREADS", "4"))
DUCKDB_MEMORY_LIMIT = os.getenv("DUCKDB_MEMORY_LIMIT", "2GB")

# logging settings
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
