#!/usr/bin/env python3
"""Test R2 permissions and operation scope"""

import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv("config/credentials.env")

import boto3
from botocore.exceptions import ClientError

def test_r2_operations():
    """Test different levels of R2 operations"""

    print("🔍 R2 Operations Permission Test")
    print("=" * 40)

    # 1. Initialize S3 client
    from config.settings import R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY

    s3_client = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name='auto'
    )

    # 2. Test listing all buckets (requires high permissions)
    print("1️⃣ Testing list all buckets:")
    try:
        response = s3_client.list_buckets()
        buckets = [bucket['Name'] for bucket in response['Buckets']]
        print(f"   ✅ Success! Found {len(buckets)} bucket(s):")
        for bucket in buckets:
            print(f"      - {bucket}")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'AccessDenied':
            print(f"   ❌ Insufficient permissions (AccessDenied)")
            print(f"   💡 Your credentials don't have permission to list all buckets")
        else:
            print(f"   ❌ Other error: {error_code}")

    # 3. Test specific bucket operations
    print("\n2️⃣ Testing specific bucket operations:")
    target_bucket = "pems-processed"

    try:
        # Test bucket existence
        s3_client.head_bucket(Bucket=target_bucket)
        print(f"   ✅ Bucket '{target_bucket}' exists and is accessible")

        # Test listing bucket contents
        response = s3_client.list_objects_v2(Bucket=target_bucket)
        if 'Contents' in response:
            objects = [obj['Key'] for obj in response['Contents']]
            print(f"   ✅ Successfully listed bucket contents: {len(objects)} object(s)")
            if objects:
                print(f"      Recent objects:")
                for obj in objects[:3]:
                    print(f"      - {obj}")
        else:
            print(f"   ✅ Bucket is empty")

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404' or error_code == 'NoSuchBucket':
            print(f"   ❌ Bucket '{target_bucket}' does not exist")
        elif error_code == '403' or error_code == 'AccessDenied':
            print(f"   ❌ Cannot access bucket '{target_bucket}' (insufficient permissions)")
        else:
            print(f"   ❌ Other error: {error_code}")

    # 4. Design philosophy explanation
    print("\n📚 Design Philosophy Explanation:")
    print("=" * 40)
    print("🎯 R2StorageHandler adopts 'single bucket dedicated design':")
    print("   - Fixed operation on 'pems-processed' bucket")
    print("   - list_files() lists files within bucket, not buckets")
    print("   - Follows principle of least privilege and single responsibility principle")
    print()
    print("🔐 Permission hierarchy:")
    print("   - Credential permissions: Can only operate specific bucket")
    print("   - Application design: Focus on single bucket")
    print("   - Security consideration: Reduce risk of permission abuse")

if __name__ == "__main__":
    test_r2_operations()