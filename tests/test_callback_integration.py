import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.monthly_download import post_download_handler


print("Testing Callback Hook")

# mock file
mock_file = Path("data/raw/2024_09_d12_station_hour.txt.gz")
mock_file.parent.mkdir(parents=True, exist_ok=True)
mock_file.write_text("mock downloaded data")

# mock metadata
mock_metadata = {
    "year": 2024,
    "month": "September",
    "district": "12",
    "file_type": "station_hour",
    "file_name": "2024_09_d12_station_hour.txt.gz",
}

print(f"\n Mock file: {mock_file}")
print(f"Running post_download_handler...")

try:
    post_download_handler(file_path=mock_file, file_metadata=mock_metadata)
    print(f"Callback Hook works")
except Exception as e:
    print(f"Error: {e}")
