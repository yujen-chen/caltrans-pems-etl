# /opt/pems-auto-downloader/scripts/monthly_download.py
#!/usr/bin/env python3
"""
monthly_download.py
------------------
This script is used to download PeMS data from CalTrans-PeMS.

Usage:
    python monthly_download.py


"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Use relative path for local development, absolute path for deployment
if os.path.exists("config/credentials.env"):
    # local development environment
    load_dotenv("config/credentials.env")
    data_path = "data"
else:
    # VPS deployment environment
    load_dotenv("/opt/pems-auto-downloader/config/credentials.env")
    data_path = "/opt/pems-auto-downloader/data"
    sys.path.insert(0, "/opt/pems-auto-downloader")

from pems.handler import PeMSHandler


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

        # Execute download
        pems.download_files(
            start_year=target_year,
            end_year=target_year,
            districts=districts,
            file_types=file_types,
            months=target_month_list,
            save_path=data_path,
        )

        print(f"✅ {target_year} {target_month} data download completed")

    except Exception as e:
        print(f"❌ Download failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
