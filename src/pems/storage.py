"""
storage.py
----------
Cloudflare R2 storage handler for PeMS data

This module provides R2 (S3-compatible) storage integration with smart upload
strategy: Processed Parquet files are always uploaded, Raw files use rolling
backup (last 12 months), and local raw files are cleaned after 30 days.

Author: Yu-Jen Chen
Created: 2025-10-13
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Import configuration
import sys
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import (
    R2_ENDPOINT,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET,
    R2_UPLOAD_ENABLED,
    R2_UPLOAD_RAW,
    R2_RAW_ROLLING_MONTHS,
    R2_LOCAL_RAW_RETENTION_DAYS,
)


LOGGER = logging.getLogger(__name__)


class R2StorageHandler:
    """
    Cloudflare R2 storage handler with smart upload strategy.

    Features:
    - Upload files to R2 (S3-compatible storage)
    - Smart strategy: Processed always uploaded, Raw rolling backup (12 months)
    - Retry mechanism for network failures (max 3 attempts)
    - Local cleanup: Remove raw files older than 30 days
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ):
        """
        Initialize R2 storage handler.

        Args:
            endpoint_url: R2 endpoint URL (default: from environment)
            access_key_id: R2 access key ID (default: from environment)
            secret_access_key: R2 secret access key (default: from environment)
            bucket_name: R2 bucket name (default: from environment)
        """
        # Load credentials from environment if not provided
        self.endpoint_url = endpoint_url or R2_ENDPOINT
        self.access_key_id = access_key_id or R2_ACCESS_KEY_ID
        self.secret_access_key = secret_access_key or R2_SECRET_ACCESS_KEY
        self.bucket_name = bucket_name or R2_BUCKET

        # Load strategy settings
        self.upload_enabled = R2_UPLOAD_ENABLED
        self.upload_raw = R2_UPLOAD_RAW
        self.raw_rolling_months = R2_RAW_ROLLING_MONTHS
        self.local_retention_days = R2_LOCAL_RAW_RETENTION_DAYS

        # Validate credentials
        if not all([self.endpoint_url, self.access_key_id, self.secret_access_key]):
            raise ValueError(
                "Missing R2 credentials. Set environment variables:\n"
                "  R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY"
            )

        # Initialize S3 client (R2 is S3-compatible)
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name='auto'  # R2 uses 'auto' region
        )

        LOGGER.info(f"R2StorageHandler initialized (bucket: {self.bucket_name})")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ClientError, ConnectionError)),
        reraise=True
    )
    def upload_file(self, local_path: Path, r2_key: str) -> str:
        """
        Upload a single file to R2 with retry mechanism.

        Args:
            local_path: Local file path
            r2_key: Object key in R2 (e.g., "processed/2024/data.parquet")

        Returns:
            S3 URI of the uploaded file (e.g., "s3://bucket/key")

        Raises:
            FileNotFoundError: If local file does not exist
            ClientError: If upload fails after retries
        """
        local_path = Path(local_path)

        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        try:
            LOGGER.info(f"Uploading to R2: {r2_key}")

            # Upload file
            self.s3_client.upload_file(
                str(local_path),
                self.bucket_name,
                r2_key
            )

            # Get object metadata
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=r2_key
            )
            file_size = response['ContentLength']

            LOGGER.info(
                f"Upload successful: {r2_key} "
                f"({file_size:,} bytes, {file_size / 1024 / 1024:.2f} MB)"
            )

            return f"s3://{self.bucket_name}/{r2_key}"

        except NoCredentialsError:
            LOGGER.error("R2 credentials not found or invalid")
            raise
        except ClientError as e:
            LOGGER.error(f"R2 upload failed: {str(e)}")
            raise

    def upload_with_strategy(
        self,
        file_path: Path,
        file_type: str,
        file_metadata: Dict[str, Any]
    ) -> Optional[str]:
        """
        Upload file using smart strategy.

        Strategy rules:
        1. Processed Parquet: Always upload to processed/YYYY/
        2. Raw (recent 12 months): Upload to raw-rolling/YYYY-MM/
        3. Raw (old): Skip upload
        4. Local Raw: Delete after 30 days

        Args:
            file_path: Local file path
            file_type: 'processed' or 'raw'
            file_metadata: File metadata dict (must contain 'year', 'month')

        Returns:
            S3 URI if uploaded, None if skipped
        """
        file_path = Path(file_path)

        if not self.upload_enabled:
            LOGGER.info("R2 upload disabled (R2_UPLOAD_ENABLED=false)")
            return None

        if file_type == 'processed':
            # Processed: Always upload
            year = file_metadata.get('year', datetime.now().year)
            r2_key = f"processed/{year}/{file_path.name}"

            try:
                s3_uri = self.upload_file(file_path, r2_key)
                LOGGER.info(f"✅ Uploaded processed: {r2_key}")
                return s3_uri
            except Exception as e:
                LOGGER.error(f"❌ Failed to upload processed: {str(e)}")
                return None

        elif file_type == 'raw':
            if not self.upload_raw:
                LOGGER.info("Raw upload disabled (R2_UPLOAD_RAW=false)")
                return None

            # Raw: Check date and apply rolling strategy
            file_date = self._parse_file_date(file_metadata)
            months_ago = (datetime.now() - file_date).days // 30

            # Upload if within rolling window (default 12 months)
            if months_ago <= self.raw_rolling_months:
                year_month = file_date.strftime('%Y-%m')
                r2_key = f"raw-rolling/{year_month}/{file_path.name}"

                try:
                    s3_uri = self.upload_file(file_path, r2_key)
                    LOGGER.info(f"🔄 Uploaded raw (rolling): {r2_key}")
                except Exception as e:
                    LOGGER.error(f"❌ Failed to upload raw: {str(e)}")
                    return None
            else:
                LOGGER.info(f"⏭️  Skipped raw upload (old): {file_path.name}")
                s3_uri = None

            # Local cleanup: Delete files older than retention period
            if months_ago > (self.local_retention_days / 30):
                try:
                    self.cleanup_old_files(file_path)
                    LOGGER.info(f"♻️  Cleaned local raw: {file_path.name}")
                except Exception as e:
                    LOGGER.warning(f"Failed to cleanup {file_path.name}: {str(e)}")

            return s3_uri

        else:
            LOGGER.warning(f"Unknown file_type: {file_type}")
            return None

    def list_files(self, prefix: str = "") -> list:
        """
        List objects in R2 bucket.

        Args:
            prefix: Prefix filter (e.g., "processed/2024/")

        Returns:
            List of object keys
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            if 'Contents' not in response:
                LOGGER.info(f"No objects found with prefix: {prefix}")
                return []

            objects = [obj['Key'] for obj in response['Contents']]
            LOGGER.info(f"Found {len(objects)} objects with prefix: {prefix}")
            return objects

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                LOGGER.error(f"Bucket does not exist: {self.bucket_name}")
                raise  # Re-raise NoSuchBucket error
            else:
                LOGGER.error(f"Failed to list objects: {str(e)}")
                return []

    def download_file(self, r2_key: str, local_path: Path) -> bool:
        """
        Download a file from R2 to local path.

        Args:
            r2_key: Object key in R2
            local_path: Local destination path

        Returns:
            True if successful, False otherwise
        """
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            LOGGER.info(f"Downloading from R2: {r2_key}")

            self.s3_client.download_file(
                self.bucket_name,
                r2_key,
                str(local_path)
            )

            LOGGER.info(f"Download successful: {local_path}")
            return True

        except ClientError as e:
            LOGGER.error(f"Failed to download {r2_key}: {str(e)}")
            return False

    def cleanup_old_files(self, file_path: Path) -> None:
        """
        Delete local file if it exists.

        Args:
            file_path: Path to file to delete
        """
        file_path = Path(file_path)

        if file_path.exists():
            file_path.unlink()
            LOGGER.info(f"Deleted local file: {file_path.name}")
        else:
            LOGGER.warning(f"File not found for cleanup: {file_path}")

    def _parse_file_date(self, file_metadata: Dict[str, Any]) -> datetime:
        """
        Parse file date from metadata.

        Args:
            file_metadata: Metadata dict containing 'year' and 'month'

        Returns:
            datetime object representing file date

        Raises:
            ValueError: If year/month not in metadata
        """
        year = file_metadata.get('year')
        month_str = file_metadata.get('month')

        if not year or not month_str:
            raise ValueError(
                f"Missing year/month in metadata: {file_metadata}"
            )

        # Convert year to int if it's a string
        year_int = int(year) if isinstance(year, str) else year

        # Convert month name to number (e.g., "January" -> 1)
        month_map = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4,
            'May': 5, 'June': 6, 'July': 7, 'August': 8,
            'September': 9, 'October': 10, 'November': 11, 'December': 12
        }

        month_num = month_map.get(month_str)
        if not month_num:
            raise ValueError(f"Invalid month name: {month_str}")

        return datetime(year_int, month_num, 1)


# Convenience functions for quick access
def upload_to_r2(local_file: Path, r2_key: str, bucket_name: str = None) -> str:
    """
    Quick upload function.

    Args:
        local_file: Local file path
        r2_key: Object key in R2
        bucket_name: Optional bucket name (default: from environment)

    Returns:
        S3 URI of uploaded file
    """
    handler = R2StorageHandler(bucket_name=bucket_name)
    return handler.upload_file(local_file, r2_key)


def list_r2_objects(prefix: str = "", bucket_name: str = None) -> list:
    """
    Quick list function.

    Args:
        prefix: Prefix filter
        bucket_name: Optional bucket name (default: from environment)

    Returns:
        List of object keys
    """
    handler = R2StorageHandler(bucket_name=bucket_name)
    return handler.list_files(prefix)
