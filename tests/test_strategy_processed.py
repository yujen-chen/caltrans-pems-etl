import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv("config/credentials.env")

from pems.storage import R2StorageHandler


print("🎯 Testing smart strategy - Processed file upload...")

test_file = Path("tests/2024_station_hour_processed.parquet")
test_file.write_text("mock Parquet data")


# mock file metadata
file_metadata = {
    "year": 2024,
    "month": "September",
    "district": "12",
    "file_type": "station_hour",
}

try:
    handler = R2StorageHandler()

    print(f"\n📤 Uploading Processed file: {test_file.name}")
    print(f"   Year: {file_metadata['year']}")

    s3_uri = handler.upload_with_strategy(
        file_path=test_file, file_type="processed", file_metadata=file_metadata
    )

    if s3_uri:
        print("upload successful")
        expected_path = f"processed/{file_metadata['year']}"
        if expected_path in s3_uri:
            print(f"✅ Path format correct: {expected_path}")

    test_file.unlink()
    print(f"test file deleted")

except Exception as e:
    print(f"Error: {e}")
