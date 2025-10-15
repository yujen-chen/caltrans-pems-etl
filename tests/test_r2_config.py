"""test R2 settings"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to Python path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv("config/credentials.env")

from config.settings import (
    R2_ENDPOINT,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET,
    R2_UPLOAD_ENABLED,
    R2_RAW_ROLLING_MONTHS,
    R2_LOCAL_RAW_RETENTION_DAYS,
)


print("R2 config test")
print(f"Endpoint: {R2_ENDPOINT}" if R2_ENDPOINT else "setting not found")
print(
    f"Access Key ID: {R2_ACCESS_KEY_ID[:10]}..."
    if R2_ACCESS_KEY_ID
    else "setting not found"
)
print(f"Secret Key: {'*' * 10}..." if R2_SECRET_ACCESS_KEY else "setting not found")
print(f"Bucket: {R2_BUCKET}")
print(f"Upload Enabled: {R2_UPLOAD_ENABLED}")
print(f"Raw Rolling Months: {R2_RAW_ROLLING_MONTHS}")
print(f"Local Retention Days: {R2_LOCAL_RAW_RETENTION_DAYS}")

# Verify required fields
if all([R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
    print("\nR2 settings completed.")
else:
    print("\nR2 not completed.")
