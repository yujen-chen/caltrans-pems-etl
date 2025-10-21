"""
Test R2 connection

Note:
    Environment variables are now loaded automatically by config.settings
    (Improvement Plan A - Proactive Loading Pattern)
"""

import sys
from pathlib import Path

# Add project root to Python path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import automatically loads environment variables
from src.pems.storage import R2StorageHandler


print("Testing R2 Connection...")

try:
    handler = R2StorageHandler()
    print(f"   R2StorageHandler initialized successfully")
    print(f"   Bucket: {handler.bucket_name}")
    print(f"   Endpoint: {handler.endpoint_url}")

    # Test list_files
    print(f"\n Listing bucket contents (first 5 objects):")
    objects = handler.list_files()

    if objects:
        for obj in objects[:5]:
            print(f"   - {obj}")
        if len(objects) > 5:
            print(f"   ... and {len(objects) - 5} more objects")
    else:
        print(f"   (bucket is empty)")

    print(f"\n R2 connection test successful!")

except Exception as e:
    print(f" R2 connection failed: {str(e)}")
    print(f" Please check")
