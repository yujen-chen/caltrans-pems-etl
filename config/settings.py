# config/settings.py
"""
Application Settings with Proactive Environment Loading

This module implements Industry Best Practice:
- Proactively loads environment variables from config/credentials.env
- Validates configuration on import
- Provides sensible defaults for development

Design Pattern:
- Similar to Django settings.py, FastAPI config, Rails config
- Configuration layer is responsible for loading credentials
- Application layer simply imports and uses
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Setup logger
logger = logging.getLogger(__name__)

# ============================================================================
# STEP 1: Project Paths
# ============================================================================
PROJECT_ROOT = Path(__file__).parent.parent

# ============================================================================
# STEP 2: Load Environment Variables (Proactive Loading)
# ============================================================================
# Load credentials from .env file if it exists
# This follows industry standard practice (Django, FastAPI, Rails, etc.)
CREDENTIALS_PATH = PROJECT_ROOT / "config" / "credentials.env"

if CREDENTIALS_PATH.exists():
    # override=False means existing environment variables take precedence
    # This allows production environments to override with Kubernetes Secrets, etc.
    load_dotenv(CREDENTIALS_PATH, override=False)
    logger.debug(f"✅ Loaded environment variables from {CREDENTIALS_PATH}")
else:
    # In production, we rely on environment variables set by the deployment system
    logger.debug(
        "⚠️  No credentials.env file found, using environment variables or defaults"
    )

# ============================================================================
# STEP 3: Data Paths
# ============================================================================
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
META_DATA_DIR = DATA_DIR / "meta"
EXPORTS_DATA_DIR = DATA_DIR / "exports"

# Ensure directories exist
for dir_path in [RAW_DATA_DIR, PROCESSED_DATA_DIR, META_DATA_DIR, EXPORTS_DATA_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ============================================================================
# STEP 4: Processing Parameters
# ============================================================================
MIN_PCT_OBS = 80
REQUIRED_DAYS_OBSERVED = 4

# ============================================================================
# STEP 5: PeMS Settings
# ============================================================================
BASE_URL = "http://pems.dot.ca.gov"
CLEARING_HOUSE_URL = (
    "{}/?srq=clearinghouse&district_id={}&yy={}&type={}&returnformat=text"
)
DISTRICTS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]

# ============================================================================
# STEP 6: R2 Storage Configuration
# ============================================================================
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "pems-processed")
R2_UPLOAD_ENABLED = os.getenv("R2_UPLOAD_ENABLED", "false").lower() == "true"
R2_UPLOAD_RAW = os.getenv("R2_UPLOAD_RAW", "true").lower() == "true"
R2_RAW_ROLLING_MONTHS = int(os.getenv("R2_RAW_ROLLING_MONTHS", "12"))
R2_LOCAL_RAW_RETENTION_DAYS = int(os.getenv("R2_LOCAL_RAW_RETENTION_DAYS", "30"))


# ============================================================================
# STEP 7: Configuration Validation
# ============================================================================
def _validate_r2_config() -> bool:
    """
    Validate R2 configuration completeness.

    This function is called automatically on module import to ensure
    all required R2 credentials are present when R2 is enabled.

    Returns:
        bool: True if R2 config is valid or R2 is disabled, False otherwise
    """
    if not R2_UPLOAD_ENABLED:
        return True

    required_vars = {
        "R2_ENDPOINT": R2_ENDPOINT,
        "R2_ACCESS_KEY_ID": R2_ACCESS_KEY_ID,
        "R2_SECRET_ACCESS_KEY": R2_SECRET_ACCESS_KEY,
        "R2_BUCKET": R2_BUCKET,
    }

    missing = [key for key, value in required_vars.items() if not value]

    if missing:
        logger.warning(
            f"⚠️  R2_UPLOAD_ENABLED=true but missing required config: {missing}. "
            "R2 features will be disabled."
        )
        return False

    logger.debug("✅ R2 configuration validated successfully")
    return True


# Validate R2 configuration on import
# If validation fails, disable R2 features to prevent runtime errors
if R2_UPLOAD_ENABLED and not _validate_r2_config():
    R2_UPLOAD_ENABLED = False
    logger.warning("⚠️  R2 configuration incomplete, R2 features have been disabled")

# ============================================================================
# STEP 8: Data Processing Constants
# ============================================================================
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
    "year",
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

# ============================================================================
# STEP 9: DuckDB Configuration
# ============================================================================
DUCKDB_PATH = os.getenv("DUCKDB_PATH", ":memory:")
DUCKDB_CACHE_SIZE = int(os.getenv("DUCKDB_CACHE_SIZE", "100"))
DUCKDB_THREADS = int(os.getenv("DUCKDB_THREADS", "4"))
DUCKDB_MEMORY_LIMIT = os.getenv("DUCKDB_MEMORY_LIMIT", "2GB")

# ============================================================================
# STEP 10: Logging Settings
# ============================================================================
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
