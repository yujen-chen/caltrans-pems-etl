#!/usr/bin/env python3
"""Check R2 permissions and existing buckets"""

import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv("config/credentials.env")

from pems.storage import R2StorageHandler

def check_r2_permissions():
    """Check R2 permissions and existing resources"""

    print("🔍 Checking R2 permissions and resources...")

    try:
        handler = R2StorageHandler()
        print(f"✅ R2 connection successful")
        print(f"   Endpoint: {handler.endpoint_url}")

        # Try to list all buckets (requires listAllMyBuckets permission)
        print(f"\n📋 Attempting to list all buckets...")
        try:
            response = handler.s3_client.list_buckets()
            buckets = [bucket['Name'] for bucket in response['Buckets']]
            print(f"✅ Found {len(buckets)} bucket(s):")
            for bucket in buckets:
                print(f"   - {bucket}")

            # Check if target bucket exists
            if handler.bucket_name in buckets:
                print(f"\n✅ Target bucket '{handler.bucket_name}' exists")
                return True
            else:
                print(f"\n❌ Target bucket '{handler.bucket_name}' does not exist")
                print(f"💡 Available buckets: {buckets}")
                return False

        except Exception as e:
            print(f"❌ Unable to list buckets: {str(e)}")

            # Check specific permissions
            print(f"\n🔐 Checking permissions...")
            try:
                # Try to access target bucket
                handler.s3_client.head_bucket(Bucket=handler.bucket_name)
                print(f"✅ Have access to bucket '{handler.bucket_name}'")
                return True
            except Exception as bucket_error:
                error_str = str(bucket_error)
                if "404" in error_str or "NoSuchBucket" in error_str:
                    print(f"❌ Bucket '{handler.bucket_name}' does not exist")
                elif "403" in error_str or "AccessDenied" in error_str:
                    print(f"❌ No access to bucket '{handler.bucket_name}'")
                else:
                    print(f"❌ Other error: {error_str}")

                print(f"\n💡 Possible solutions:")
                print(f"   1. Manually create bucket '{handler.bucket_name}' in Cloudflare R2 console")
                print(f"   2. Update R2 credentials permissions (if automatic bucket creation is needed)")
                print(f"   3. Use existing bucket (if available)")

                return False

    except ValueError as e:
        print(f"❌ R2 configuration error: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Unknown error: {str(e)}")
        return False


if __name__ == "__main__":
    success = check_r2_permissions()
    sys.exit(0 if success else 1)