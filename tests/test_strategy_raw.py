import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv("config/credentials.env")

from pems.storage import R2StorageHandler

print("Testing rolling raw backup")

test_file = Path("tests/2024_09_d12_station_hour.txt.gz")
test_file.write_text("mock text file")

# recent file
print("Recent - within 3 months")
metadata_recent = {
    "year": datetime.now().year,
    "month": (datetime.now() - timedelta(days=90)).strftime("%B"),
    "district": "12",
}

try:
    handler = R2StorageHandler()

    s3_uri = handler.upload_with_strategy(
        file_path=test_file, file_type="raw", file_metadata=metadata_recent
    )
    if s3_uri:
        print(f"upload completed: {s3_uri}")
        if "raw-rolling" in s3_uri:
            print(f"Correct path: raw-rolling/")
except Exception as e:
    print(f"error: {e}")


# old file
print("Old - over 15 months")
# Old test (create separate file)
test_file_old = Path("tests/2023_01_d12_station_hour.txt.gz")
test_file_old.write_text("mock old text file")

metadata_old = {
    "year": datetime.now().year - 2,
    "month": "January",
    "district": "12",
}


try:
    handler = R2StorageHandler()

    s3_uri = handler.upload_with_strategy(
        file_path=test_file_old, file_type="raw", file_metadata=metadata_old
    )
    if s3_uri is None:
        print(f"Correct: pass upload")
    else:
        print(f"Wrong: uploaded")

except Exception as e:
    print(f"error: {e}")
