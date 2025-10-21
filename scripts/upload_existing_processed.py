#!/usr/bin/env python3
"""
upload_existing_processed.py
-----------------------------
One-time script to upload existing processed parquet files to R2.

This script is used to sync existing processed files to R2 cloud storage
before enabling automatic upload in data_processor.py.

Usage:
    uv run python scripts/upload_existing_processed.py

Note:
    Environment variables are now loaded automatically by config.settings
    (Improvement Plan A - Proactive Loading Pattern)

Author: Yu-Jen Chen
Created: 2025-10-17
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import config.settings (which automatically loads environment variables)
from config.settings import PROCESSED_DATA_DIR, R2_UPLOAD_ENABLED
from src.pems.storage import R2StorageHandler


def main():
    """Upload all existing processed parquet files to R2"""

    print("=== Upload Existing Processed Files to R2 ===\n")

    # Check if R2 is enabled
    if not R2_UPLOAD_ENABLED:
        print("❌ R2 upload is disabled (R2_UPLOAD_ENABLED=false)")
        print("Please enable R2 in config/settings.py or .env file")
        sys.exit(1)

    # Find all processed parquet files
    # MODIFIED: Only upload 2019 for testing (user will test 2020-2025 themselves)
    processed_files = sorted(PROCESSED_DATA_DIR.glob("2019_station_hour_processed.parquet"))

    if not processed_files:
        print(f"❌ No 2019 processed file found in {PROCESSED_DATA_DIR}")
        print("Note: This script is configured to only upload 2019 for testing.")
        sys.exit(1)

    print(f"Found {len(processed_files)} processed files:\n")
    for file_path in processed_files:
        file_size_mb = file_path.stat().st_size / 1024 / 1024
        print(f"  - {file_path.name} ({file_size_mb:.1f} MB)")

    total_size_mb = sum(f.stat().st_size for f in processed_files) / 1024 / 1024
    print(f"\nTotal size: {total_size_mb:.1f} MB")

    # Confirm upload
    print("\n⚠️  This will upload all processed files to R2 cloud storage.")
    confirm = input("Continue? (yes/no): ").strip().lower()

    if confirm != "yes":
        print("Upload cancelled")
        sys.exit(0)

    # Initialize R2 handler
    try:
        r2_handler = R2StorageHandler()
        print("\n✅ R2 connection established")
    except Exception as e:
        print(f"\n❌ Failed to initialize R2 handler: {e}")
        sys.exit(1)

    # Upload each file
    print("\n--- Starting upload ---\n")

    success_count = 0
    failed_files = []

    for idx, file_path in enumerate(processed_files, 1):
        year = file_path.stem.split("_")[0]  # Extract year from filename

        print(f"[{idx}/{len(processed_files)}] Uploading {file_path.name}...")

        try:
            # Prepare file metadata
            file_metadata = {
                "year": year,
                "month": "yearly_aggregate",
            }

            # Upload using smart strategy
            s3_uri = r2_handler.upload_with_strategy(
                file_path=file_path,
                file_type="processed",
                file_metadata=file_metadata,
            )

            if s3_uri:
                success_count += 1
                print(f"  ✅ Success: {s3_uri}\n")
            else:
                failed_files.append(file_path.name)
                print(f"  ⚠️  Upload was skipped or failed\n")

        except Exception as e:
            failed_files.append(file_path.name)
            print(f"  ❌ Error: {str(e)}\n")

    # Summary
    print("\n=== Upload Summary ===")
    print(f"Total files: {len(processed_files)}")
    print(f"✅ Successful: {success_count}")
    print(f"❌ Failed: {len(failed_files)}")

    if failed_files:
        print("\nFailed files:")
        for filename in failed_files:
            print(f"  - {filename}")
        sys.exit(1)
    else:
        print("\n🎉 All processed files uploaded successfully!")


if __name__ == "__main__":
    main()
