#!/usr/bin/env python3
"""
Example usage script for CalTrans PeMS data downloader
Usage: uv run python example_usage.py
"""

import os
import sys
from pems.handler import PeMSHandler


def main():
    """Main function to test PeMS data downloading."""

    # Configuration - modify these as needed
    USERNAME = "sebi.goodfellow@utoronto.ca"  # Replace with your PeMS username
    PASSWORD = "xG*apple3f"  # Replace with your PeMS password

    # Test parameters
    START_YEAR = 2024  # Use 2024 instead of 2025 for available data
    END_YEAR = 2024
    DISTRICTS = ["12"]  # District 12 (Orange County)
    FILE_TYPES = ["station_hour"]  # Hourly station data
    MONTHS = ["April", "May"]  # April and May

    try:
        print("🚀 Starting CalTrans PeMS data download test...")
        print(f"📅 Year: {START_YEAR}")
        print(f"🏛️  Districts: {', '.join(DISTRICTS)}")
        print(f"📊 File types: {', '.join(FILE_TYPES)}")
        print(f"📅 Months: {', '.join(MONTHS)}")
        print()

        # Initialize PeMS handler
        print("🔐 Connecting to PeMS...")
        pems = PeMSHandler(username=USERNAME, password=PASSWORD)

        # Check available file types
        print("📋 Available file types:")
        file_types = pems.get_file_types()
        for ft in file_types:
            print(f"  - {ft}")
        print()

        # Check available districts for our file type
        print(f"🏛️  Available districts for {FILE_TYPES[0]}:")
        districts = pems.get_districts(FILE_TYPES[0])
        for d in districts:
            print(f"  - District {d}")
        print()

        # Get available files
        print("🔍 Checking available files...")
        files = pems.get_files(
            start_year=START_YEAR,
            end_year=END_YEAR,
            districts=DISTRICTS,
            file_types=FILE_TYPES,
            months=MONTHS,
        )

        if not files:
            print("❌ No files found for the specified criteria.")
            print("💡 Try:")
            print("   - Using year 2023 or 2024 instead of 2025")
            print("   - Checking different districts")
            print("   - Using different file types")
            return

        print(f"✅ Found {len(files)} files:")
        for file in files[:5]:  # Show first 5 files
            print(f"  - {file['file_name']} ({file['megabites']} MB)")
        if len(files) > 5:
            print(f"  ... and {len(files) - 5} more")
        print()

        # Download files
        print("⬇️  Starting download...")
        pems.download_files(
            start_year=START_YEAR,
            end_year=END_YEAR,
            districts=DISTRICTS,
            file_types=FILE_TYPES,
            months=MONTHS,
        )

        print("✅ Download complete!")
        print(f"📁 Files saved to: {os.path.join(os.getcwd(), 'data')}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("\n🔧 Troubleshooting:")
        print("1. Check your username and password")
        print("2. Ensure you have internet connectivity")
        print("3. Try different years (2023-2024 have more data)")
        print("4. Try different districts or file types")
        sys.exit(1)


if __name__ == "__main__":
    main()
