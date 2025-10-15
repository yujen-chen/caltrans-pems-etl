import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# for test only
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv("config/credentials.env")

from pems.storage import R2StorageHandler


"""

📋 Problem Analysis

1. R2 connection is normal: credentials can connect to R2 endpoint
2. Limited permissions:
- ❌ Cannot list buckets (AccessDenied)
- ❌ Cannot create bucket (AccessDenied)
- ❌ Target bucket pems-processed does not exist

This is industry-standard security configuration: Principle of Least
Privilege. Applications are only given necessary permissions, and these
credentials are only granted access to specific buckets.

💡 Solution

Manually creating the bucket is currently the most suitable approach:

1. Log in to Cloudflare Dashboard
2. Go to R2 Object Storage
3. Create bucket: pems-processed
4. Re-run the test

This is also industry-standard DevOps practice:
- Partial functionality of Infrastructure as Code (IaC)
- Manual intervention for high-privilege operations
- Applications only handle tasks within daily operational permissions

"""


def check_and_create_bucket(handler):
    """Check if bucket exists, create if not"""

    print("🪣 Checking R2 Bucket...")

    try:
        # Try to list objects to check if bucket exists
        objects = handler.list_files()
        print(f"✅ Bucket '{handler.bucket_name}' exists")
        print(f"   Existing objects count: {len(objects)}")
        return True

    except Exception as e:
        error_str = str(e)
        if "NoSuchBucket" in error_str:
            print(f"❌ Bucket '{handler.bucket_name}' does not exist")
            print(f"🔧 Attempting to create bucket...")

            try:
                # Use boto3 to create bucket
                handler.s3_client.create_bucket(Bucket=handler.bucket_name)
                print(f"✅ Bucket '{handler.bucket_name}' created successfully!")

                # Verify creation
                handler.list_files()
                print(f"✅ Bucket creation verified")
                return True

            except Exception as create_error:
                print(f"❌ Bucket creation failed: {str(create_error)}")
                print(f"\n💡 Please manually create bucket in Cloudflare R2 console:")
                print(f"   1. Log in to Cloudflare Dashboard")
                print(f"   2. Go to R2 Object Storage")
                print(f"   3. Create bucket: '{handler.bucket_name}'")
                print(f"   4. Re-run this test")
                return False
        else:
            print(f"❌ Error checking bucket: {str(e)}")
            return False


def main():
    """Main test flow"""

    print("🧪 Phase 1 Test Stage 2: File Upload Functionality Test")
    print("=" * 50)

    try:
        # Initialize R2 handler
        handler = R2StorageHandler()
        print(f"✅ R2StorageHandler initialized successfully")
        print(f"   Endpoint: {handler.endpoint_url}")
        print(f"   Bucket: {handler.bucket_name}")

        # Check and create bucket
        print()
        bucket_ready = check_and_create_bucket(handler)
        if not bucket_ready:
            return False

        # Create test file
        print()
        test_file = Path("tests/test_data.txt")
        test_file.parent.mkdir(exist_ok=True)

        test_content = f"""Phase 1 R2 Upload Test File
Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
File Purpose: Verify R2 Upload Functionality
Phase: ETL Modernization Phase 1
"""
        test_file.write_text(test_content, encoding="utf-8")
        print(f"✅ Created test file: {test_file}")
        print(f"   File size: {test_file.stat().st_size} bytes")

        # Execute upload test
        print()
        r2_key = "test/phase1_test.txt"
        print(f"📤 Uploading to R2: {r2_key}")

        s3_uri = handler.upload_file(test_file, r2_key)
        print(f"✅ Upload successful: {s3_uri}")

        # Verify file exists
        print()
        print(f"🔍 Verifying file exists...")
        objects = handler.list_files(prefix="test/")

        if r2_key in objects:
            print(f"✅ File exists in R2: {r2_key}")
        else:
            print(f"❌ File not found")
            print(f"   Found objects: {objects}")
            return False

        # Clean up test file
        print()
        test_file.unlink()
        print(f"🧹 Local test file cleaned up")

        print()
        print("🎉 R2 Upload Test Completed!")
        print("   ✅ Bucket check/create")
        print("   ✅ File upload")
        print("   ✅ File verification")
        print("   ✅ Cleanup completed")

        return True

    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
