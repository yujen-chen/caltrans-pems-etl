# /opt/pems-auto-downloader/scripts/monthly_download.py
#!/usr/bin/env python3
"""
monthly_download.py
------------------
This script is used to download PeMS data from CalTrans-PeMS.

Usage:
    uv run python scripts/monthly_download.py


"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# IMPORTANT: Load environment variables BEFORE importing config.settings
# This ensures config.settings reads the correct environment variable values
if os.path.exists("config/credentials.env"):
    # local development environment
    load_dotenv("config/credentials.env")
else:
    # VPS deployment environment
    load_dotenv("/opt/pems-auto-downloader/config/credentials.env")

# Import config.settings AFTER loading environment variables
from config.settings import RAW_DATA_DIR, R2_UPLOAD_ENABLED

# Set data path
if os.path.exists("config/credentials.env"):
    data_path = str(RAW_DATA_DIR)
else:
    data_path = "/opt/pems-auto-downloader/data"

# Import other modules
from src.pems.core.handler import PeMSHandler
from src.pems.storage import R2StorageHandler


def post_download_handler(file_path, file_metadata):
    """
    Post-download callback handler for R2 upload.

    Args:
        file_path (Path): Downloaded file path
        file_metadata (dict): File metadata (year, month, district, etc.)
    """
    print(f"Handling file: {file_path.name}")

    try:
        # Check if R2 upload is enabled
        if not R2_UPLOAD_ENABLED:
            print("R2 upload is not enabled（R2_UPLOAD_ENABLED=false）")
            return

        # Initialize R2 handler
        r2_handler = R2StorageHandler()

        # Upload using smart strategy
        # Note: Currently uploading raw files; processed files will be added
        # when integrating with data_processor.py in future phases
        r2_handler.upload_with_strategy(
            file_path=file_path, file_type="raw", file_metadata=file_metadata
        )

        print(f"R2 upload completed: {file_path.name}")

    except Exception as e:
        print(f"R2 upload failed: {str(e)}")
        # Don't interrupt the download process


def main():
    """Main execution function"""

    username = os.getenv("PEMS_USERNAME")
    password = os.getenv("PEMS_PASSWORD")

    if not username or not password:
        print("error: cannot find login credentials")
        sys.exit(1)

    # Calculate the month to download (last month's data)
    today = datetime.now()
    last_month = today.replace(day=1) - timedelta(days=1)
    target_year = last_month.year
    target_month = last_month.strftime("%B")
    target_month_list = [target_month]

    print(f"Start Downloading Data for Year: {target_year} Month: {target_month} ...")

    try:
        # Create PeMS connection
        pems = PeMSHandler(username=username, password=password)

        # Set download parameters
        districts = ["12"]
        file_types = ["station_hour"]

        # Execute download with R2 upload callback
        pems.download_files(
            start_year=target_year,
            end_year=target_year,
            districts=districts,
            file_types=file_types,
            months=target_month_list,
            save_path=data_path,
            post_download_callback=post_download_handler,
        )

        print(f"{target_year} {target_month} data download completed")

    except Exception as e:
        print(f"Download failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
