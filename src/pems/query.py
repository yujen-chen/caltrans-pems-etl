"""
DuckDB Query Engine for PeMS Traffic Data Analysis

This module provides a unified query interface for analyzing traffic data stored in
Parquet format, supporting both local and cloud (R2) data sources.

Industry Alignment:
- Data Access Layer (DAL) pattern: Separates query logic from storage
- OLAP optimization: Columnar storage + vectorized execution
- Lakehouse architecture: Query data lake files directly (no ETL needed)

Performance Benefits:
- 10-100x faster than pandas for large datasets
- Automatic query optimization (predicate pushdown, column pruning)
- Support for complex analytics (window functions, aggregations)
"""

import duckdb
import logging
from pathlib import Path
from typing import Optional, Union, List, Any, Dict
import pandas as pd
from collections import OrderedDict
import hashlib
import time

from config.settings import (
    PROCESSED_DATA_DIR,
    DUCKDB_PATH,
    DUCKDB_THREADS,
    DUCKDB_MEMORY_LIMIT,
    DUCKDB_CACHE_SIZE,
    DUCKDB_CACHE_TTL,
    R2_UPLOAD_ENABLED,
    R2_ENDPOINT,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QueryCache:
    """
    LRU (Least Recently Used) cache for query results.

    Industry Alignment:
    - Similar to: Redis (distributed cache), Memcached, Application-level cache
    - Pattern: Cache-aside pattern (application manages cache)
    - Use case: Reduce database load, improve dashboard response time

    Design Decisions:
    - LRU eviction: Remove least recently used items when cache is full
    - TTL (Time To Live): Auto-expire stale results after X seconds
    - Cache key: Hash of (SQL + params + data_source) for uniqueness

    Performance Benefits:
    - Cache hit: <1ms (in-memory lookup)
    - Cache miss: 100-1000ms (DuckDB query)
    - Target hit rate: >50% for dashboard workloads

    Industry Comparison:
    - Redis: Distributed, persistent, complex setup
    - This: In-process, ephemeral, simple setup
    - Trade-off: No cross-process sharing, but zero infra overhead

    Attributes:
        cache: OrderedDict for LRU behavior (preserves insertion order)
        max_size: Maximum number of cached items (防止記憶體溢出)
        ttl: Time-to-live in seconds (freshness guarantee)
        timestamps: Track when each item was cached
        hit_count: Cache hit counter (for metrics)
        miss_count: Cache miss counter (for metrics)
    """

    def __init__(self, max_size: int = 100, ttl: int = 300):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of cached query results (default: 100)
            ttl: Time-to-live in seconds (default: 300 = 5 minutes)

        Industry Practice:
        - Max size: Balance memory vs hit rate (100-1000 typical)
        - TTL: Balance freshness vs performance (1-10 minutes typical)
        - Similar to: Redis EXPIRE, Memcached expiration

        Example:
            >>> cache = QueryCache(max_size=50, ttl=600)  # 50 items, 10 min TTL
        """
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl
        self.timestamps = {}

        # Metrics for monitoring (see Phase 2.3 requirements)
        self.hit_count = 0
        self.miss_count = 0

        logger.info(f"✅ QueryCache initialized (max_size={max_size}, ttl={ttl}s)")

    def _generate_key(
        self, sql: str, params: Optional[List[Any]], data_source: str
    ) -> str:
        """
        Generate unique cache key from query components.

        Uses MD5 hash for compact keys (security not needed here).

        Args:
            sql: SQL query string
            params: Query parameters (or None)
            data_source: "local" or "r2"

        Returns:
            str: MD5 hash of query signature

        Industry Practice:
        - Hash function: MD5 (fast, compact) or SHA256 (secure, slower)
        - Key components: All factors that affect query results
        - Similar to: HTTP ETag generation, database query fingerprinting

        Example:
            >>> key = cache._generate_key("SELECT * FROM t WHERE id=?", [5], "local")
            >>> print(key)  # "a3f8c9b2e1d0..."
        """
        # Combine all query components into a single string
        params_str = str(params) if params else ""
        content = f"{sql}:{params_str}:{data_source}"

        # Hash for compact storage (128-bit MD5 vs unlimited string length)
        # Industry note: MD5 is deprecated for security, but fine for cache keys
        return hashlib.md5(content.encode()).hexdigest()

    def get(
        self, sql: str, params: Optional[List[Any]], data_source: str
    ) -> Optional[pd.DataFrame]:
        """
        Retrieve cached query result.

        Args:
            sql: SQL query
            params: Query parameters
            data_source: Data source identifier

        Returns:
            pd.DataFrame if cache hit and not expired, None otherwise

        Side Effects:
            - Updates hit_count or miss_count
            - Moves accessed item to end (LRU maintenance)
            - Removes expired items

        Industry Practice:
        - Cache invalidation: Check TTL before returning
        - LRU update: Move accessed item to end (most recently used)
        - Metrics: Track hit/miss for monitoring

        Example:
            >>> result = cache.get("SELECT * FROM t", None, "local")
            >>> if result is not None:
            >>>     print("Cache hit!")
            >>> else:
            >>>     print("Cache miss, need to query database")
        """
        key = self._generate_key(sql, params, data_source)

        # Check if key exists
        if key not in self.cache:
            self.miss_count += 1
            return None

        # Check if expired (TTL validation)
        age = time.time() - self.timestamps[key]
        if age > self.ttl:
            # Remove expired entry
            # Industry note: Lazy expiration (check on access, not proactive)
            del self.cache[key]
            del self.timestamps[key]
            self.miss_count += 1
            logger.debug(
                f"Cache expired: key={key[:8]}... (age={age:.1f}s > ttl={self.ttl}s)"
            )
            return None

        # Cache hit! Move to end (mark as recently used)
        # Industry note: OrderedDict.move_to_end() is O(1) operation
        self.cache.move_to_end(key)
        self.hit_count += 1

        logger.debug(f"Cache hit: key={key[:8]}... (age={age:.1f}s)")
        return self.cache[key]

    def set(
        self,
        sql: str,
        params: Optional[List[Any]],
        data_source: str,
        result: pd.DataFrame,
    ):
        """
        Store query result in cache.

        Args:
            sql: SQL query
            params: Query parameters
            data_source: Data source identifier
            result: Query result DataFrame

        Side Effects:
            - May evict oldest item if cache is full (LRU eviction)
            - Updates timestamps for TTL tracking

        Industry Practice:
        - Eviction policy: LRU (remove least recently used)
        - Atomic operation: Remove old + insert new (no intermediate state)
        - Memory management: Limit cache size to prevent OOM

        Example:
            >>> df = engine.execute("SELECT * FROM t").df()
            >>> cache.set("SELECT * FROM t", None, "local", df)
        """
        key = self._generate_key(sql, params, data_source)

        # Evict oldest item if cache is full
        # Industry note: Alternative policies: LFU (least frequently used), FIFO
        if len(self.cache) >= self.max_size and key not in self.cache:
            # Remove oldest item (FIFO order in OrderedDict)
            # Industry note: popitem(last=False) is Pythonic way to remove first item (LRU eviction)
            oldest_key, _ = self.cache.popitem(last=False)
            del self.timestamps[oldest_key]
            logger.debug(f"Cache full, evicted: key={oldest_key[:8]}...")

        # Store result and timestamp
        self.cache[key] = result
        self.timestamps[key] = time.time()

        logger.debug(
            f"Cache set: key={key[:8]}... (size={len(self.cache)}/{self.max_size})"
        )

    def clear(self):
        """
        Clear all cached items.

        Use Cases:
        - Manual cache invalidation (e.g., after data update)
        - Memory pressure (free up RAM)
        - Testing (clean slate)

        Industry Practice:
        - Similar to: Redis FLUSHDB, Memcached flush_all
        - When to use: Data refresh, deployment, debugging

        Example:
            >>> cache.clear()
            >>> print("Cache cleared, all queries will hit database")
        """
        size = len(self.cache)
        self.cache.clear()
        self.timestamps.clear()
        logger.info(f"✅ Cache cleared ({size} items removed)")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache performance metrics.

        Returns:
            dict: Performance statistics including:
                - total_queries: Total cache accesses (hits + misses)
                - cache_hits: Number of successful cache lookups
                - cache_misses: Number of database queries needed
                - cache_hit_rate: Percentage of cache hits (0.0-1.0)
                - cache_size: Current number of cached items
                - cache_max_size: Maximum cache capacity

        Industry Practice:
        - Monitoring: Export to Prometheus, Grafana, DataDog
        - SLO (Service Level Objective): Target >50% hit rate
        - Alerting: Alert if hit rate drops below threshold

        Example:
            >>> stats = cache.get_stats()
            >>> print(f"Cache hit rate: {stats['cache_hit_rate']:.1%}")
            >>> print(f"Cache usage: {stats['cache_size']}/{stats['cache_max_size']}")

            >>> # Export to monitoring system
            >>> prometheus_client.Gauge('cache_hit_rate').set(stats['cache_hit_rate'])
        """
        total = self.hit_count + self.miss_count
        hit_rate = self.hit_count / total if total > 0 else 0.0

        return {
            "total_queries": total,
            "cache_hits": self.hit_count,
            "cache_misses": self.miss_count,
            "cache_hit_rate": hit_rate,
            "cache_size": len(self.cache),
            "cache_max_size": self.max_size,
        }


class DuckDBQueryEngine:
    """
    Unified query engine for traffic data analysis.

    This class provides a high-level interface to DuckDB, optimized for analyzing
    PeMS traffic data stored in Parquet format.

    Design Patterns:
    - Singleton-like connection pooling: Reuse database connection
    - Lazy initialization: Only setup data sources when first accessed
    - Fail-fast: Validate configuration during initialization

    Industry Comparison:
    - Similar to: Spark DataFrame API, Presto/Trino connectors
    - Advantages over pandas: Column-oriented, vectorized, query optimization

    Attributes:
        db: DuckDB connection object
        data_source: "local" or "r2" (determines data location)
        cache: Simple dict-based query result cache
    """

    def __init__(
        self,
        db_path: str = DUCKDB_PATH,
        data_source: str = "local",
        cache_size: int = DUCKDB_CACHE_SIZE,
    ):
        """
        Initialize DuckDB query engine.

        Args:
            db_path: Database path (":memory:" for in-memory, or file path for persistent)
            data_source: "local" (processed/*.parquet) or "r2" (s3://bucket/processed/)
            cache_size: Maximum number of cached query results (LRU eviction)

        Industry Practice:
        - In-memory DB: Fast but volatile (development/testing)
        - Persistent DB: Durable storage (production)
        - Similar to: Redis (in-memory), PostgreSQL (persistent)

        Raises:
            RuntimeError: If DuckDB initialization fails
        """
        logger.info(f"Initializing DuckDB query engine (source: {data_source})")

        try:
            # Create DuckDB connection
            # Industry note: Similar to psycopg2.connect() for PostgreSQL
            self.db = duckdb.connect(db_path)
            self.data_source = data_source

            # Initialize LRU cache (Phase 2.3)
            # Industry note: Upgraded from simple dict to proper LRU cache
            self.cache = QueryCache(max_size=cache_size, ttl=DUCKDB_CACHE_TTL)

            # Setup database configuration
            self._setup_database()

            logger.info("✅ DuckDB engine initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize DuckDB: {e}")
            raise RuntimeError(f"DuckDB initialization failed: {e}")

    def _setup_database(self):
        """
        Configure DuckDB for optimal performance.

        This method sets up:
        1. Performance parameters (threads, memory limit)
        2. Extensions (httpfs for S3 access)
        3. Data source views (local or R2)

        Industry Practice:
        - Similar to PostgreSQL postgresql.conf tuning
        - Spark: spark.conf.set() configuration
        - Key metrics: threads (parallelism), memory (OOM prevention)

        Performance Tuning:
        - Threads: Utilize multi-core CPUs (default: 4 cores)
        - Memory: Prevent OOM by capping usage (default: 2GB)
        - httpfs: Enable S3-compatible storage access (Cloudflare R2)
        """
        try:
            # Install and load httpfs extension for S3/R2 access
            # Industry note: Similar to PostgreSQL extensions (postgis, pg_cron)
            self.db.execute("INSTALL httpfs")
            self.db.execute("LOAD httpfs")
            logger.info("✅ Loaded httpfs extension (S3-compatible storage)")

            # Set performance parameters
            # Industry standard: threads = CPU cores - 1 (leave 1 for OS)
            self.db.execute(f"SET threads={DUCKDB_THREADS}")
            self.db.execute(f"SET memory_limit='{DUCKDB_MEMORY_LIMIT}'")
            logger.info(
                f"✅ Performance config: {DUCKDB_THREADS} threads, "
                f"{DUCKDB_MEMORY_LIMIT} memory limit"
            )

            # Setup data source (local or R2)
            if self.data_source == "local":
                self._setup_local_data()
            elif self.data_source == "r2":
                if R2_UPLOAD_ENABLED:
                    self._setup_r2_data()
                else:
                    logger.warning(
                        "⚠️  R2 requested but R2_UPLOAD_ENABLED=false, "
                        "falling back to local data"
                    )
                    self.data_source = "local"
                    self._setup_local_data()
            else:
                logger.warning(
                    f"⚠️  Unknown data source '{self.data_source}', "
                    "falling back to local data"
                )
                self.data_source = "local"
                self._setup_local_data()

        except Exception as e:
            logger.error(f"❌ Database setup failed: {e}")
            raise

    def _setup_local_data(self):
        """
        Setup local Parquet files as a queryable view.

        Creates a unified "traffic_data" view from all processed Parquet files:
        - Scans: data/processed/*_station_hour_processed.parquet
        - Combines: All years into a single virtual table
        - Optimization: Uses Parquet metadata for fast filtering

        Industry Practice:
        - Similar to: Hive external tables, Presto/Trino connectors
        - Performance: Column pruning (read only needed columns)
        - Scalability: DuckDB can handle 100GB+ Parquet files

        SQL View Pattern:
        ```sql
        CREATE VIEW traffic_data AS
        SELECT * FROM read_parquet('processed/*.parquet')
        ```

        Why views? (vs loading data)
        - Lazy evaluation: Data only read when queried
        - Memory efficient: No upfront loading cost
        - Fresh data: Always reads latest files
        """
        logger.info("Setting up local Parquet data source...")

        # Find all processed Parquet files
        processed_files = list(
            PROCESSED_DATA_DIR.glob("*_station_hour_processed.parquet")
        )

        if not processed_files:
            logger.warning(f"⚠️  No processed files found in {PROCESSED_DATA_DIR}")
            return

        # Create unified view using DuckDB's read_parquet()
        # Industry note: Similar to Spark's spark.read.parquet()
        file_pattern = str(PROCESSED_DATA_DIR / "*_station_hour_processed.parquet")

        try:
            # Create view (virtual table, no data copied)
            self.db.execute(
                f"""
                CREATE OR REPLACE VIEW traffic_data AS
                SELECT * FROM read_parquet('{file_pattern}')
            """
            )

            # Log summary statistics
            row_count = self.db.execute(
                "SELECT COUNT(*) as cnt FROM traffic_data"
            ).df()["cnt"][0]
            logger.info(
                f"✅ Loaded {len(processed_files)} Parquet files "
                f"({row_count:,} total rows) into 'traffic_data' view"
            )

            # Show available years (for debugging)
            years = (
                self.db.execute("SELECT DISTINCT year FROM traffic_data ORDER BY year")
                .df()["year"]
                .tolist()
            )
            logger.info(f"📅 Available years: {years}")

        except Exception as e:
            logger.error(f"❌ Failed to create traffic_data view: {e}")
            raise

    def _setup_r2_data(self):
        """
        Setup Cloudflare R2 (S3-compatible) data source.

        Configures DuckDB to query Parquet files directly from R2 cloud storage:
        - No download required: Streams data over HTTP
        - Column pruning: Only fetches needed columns (bandwidth savings)
        - Range requests: HTTP byte-range for efficient access

        Industry Practice:
        - AWS Athena: Query S3 data with SQL
        - Snowflake External Tables: Query cloud storage
        - Databricks Delta Lake: Lakehouse architecture

        Performance:
        - Network overhead: ~100-500ms latency per query
        - Bandwidth: Parquet compression reduces transfer
        - Cost: R2 egress is free (unlike S3)

        Security:
        - Uses IAM-like credentials (access_key_id + secret)
        - HTTPS encryption in transit
        - No data stored locally (compliance friendly)

        Raises:
            Exception: If R2 configuration is invalid or connection fails
        """
        logger.info("Setting up R2 cloud data source...")

        try:
            # Import here to avoid circular dependency
            from src.pems.storage import R2StorageHandler

            r2_handler = R2StorageHandler()

            # List available files in R2 (metadata only, no download)
            processed_files = r2_handler.list_files(prefix="processed/")

            if not processed_files:
                logger.warning("⚠️  No processed files found in R2")
                return

            # Configure S3-compatible access
            # Industry note: Similar to AWS Glue Catalog configuration
            endpoint_clean = R2_ENDPOINT.replace("https://", "").replace("http://", "")

            self.db.execute(f"SET s3_endpoint='{endpoint_clean}'")
            self.db.execute(f"SET s3_access_key_id='{R2_ACCESS_KEY_ID}'")
            self.db.execute(f"SET s3_secret_access_key='{R2_SECRET_ACCESS_KEY}'")
            self.db.execute("SET s3_url_style='path'")  # R2 uses path-style URLs

            # Create view pointing to R2 bucket
            # Use ** for recursive glob to match files in subdirectories (processed/YYYY/*.parquet)
            s3_pattern = (
                f"s3://{R2_BUCKET}/processed/**/*_station_hour_processed.parquet"
            )

            self.db.execute(
                f"""
                CREATE OR REPLACE VIEW traffic_data AS
                SELECT * FROM read_parquet('{s3_pattern}')
            """
            )

            logger.info(
                f"✅ Loaded {len(processed_files)} R2 files into 'traffic_data' view"
            )

        except Exception as e:
            logger.error(f"❌ R2 setup failed: {e}")
            logger.info("🔄 Falling back to local data source")

            # Fallback to local data
            # Industry pattern: Graceful degradation (use cached/local data if cloud fails)
            self.data_source = "local"
            self._setup_local_data()

    def execute(
        self, sql: str, params: Optional[List[Any]] = None, use_cache: bool = True
    ) -> duckdb.DuckDBPyRelation:
        """
        Execute raw SQL query with optional caching.

        This is the low-level query interface, supporting full SQL syntax:
        - SELECT, JOIN, GROUP BY, window functions
        - CTEs (WITH clause), subqueries
        - DuckDB-specific functions (MEDIAN, QUANTILE, etc.)

        Args:
            sql: SQL query string
            params: Optional parameters for parameterized queries (防止 SQL injection)
            use_cache: Whether to use query cache (default: True)

        Returns:
            DuckDBPyRelation: Query result (can convert to DataFrame, Arrow, etc.)

        Industry Practice:
        - Similar to: psycopg2.cursor.execute(), SQLAlchemy.execute()
        - Security: Always use parameterized queries for user input
        - Performance: DuckDB auto-optimizes query plan (like PostgreSQL EXPLAIN)
        - Caching: Phase 2.3 enhancement for repeated queries

        Cache Behavior (Phase 2.3):
        - Cache hit: Returns cached result in <1ms
        - Cache miss: Executes query and caches result
        - Cache bypass: Set use_cache=False for fresh data

        Example:
            >>> # With cache (default)
            >>> result = engine.execute("SELECT * FROM traffic_data WHERE route = ?", [5])
            >>> df = result.df()

            >>> # Bypass cache (for write queries or fresh data)
            >>> result = engine.execute("INSERT INTO ...", use_cache=False)
        """
        try:
            # Phase 2.3: Check cache first (only for SELECT queries)
            # Industry note: Only cache read queries, not writes (INSERT/UPDATE/DELETE)
            is_select = sql.strip().upper().startswith("SELECT")

            if use_cache and is_select:
                # Try to get cached result
                cached_df = self.cache.get(sql, params, self.data_source)
                if cached_df is not None:
                    # Cache hit! Return as DuckDBPyRelation for API consistency
                    # Industry note: Need to convert DataFrame back to DuckDB relation
                    return self.db.from_df(cached_df)

            # Cache miss or cache bypassed - execute query
            if params:
                result = self.db.execute(sql, params)
            else:
                result = self.db.execute(sql)

            # Phase 2.3: Cache the result (only for SELECT queries)
            if use_cache and is_select:
                result_df = result.df()
                self.cache.set(sql, params, self.data_source, result_df)
                # Return as relation (for API consistency)
                return self.db.from_df(result_df)

            return result

        except Exception as e:
            logger.error(f"❌ Query execution failed: {e}")
            logger.error(f"SQL: {sql}")
            raise

    def query_to_df(self, sql: str, params: Optional[List[Any]] = None) -> pd.DataFrame:
        """
        Execute query and return pandas DataFrame.

        Convenience method that wraps execute() + .df() conversion.

        Args:
            sql: SQL query string
            params: Optional query parameters

        Returns:
            pd.DataFrame: Query results as pandas DataFrame

        Industry Practice:
        - Similar to: pandas.read_sql(), SQLAlchemy query.all()
        - Use case: Integrate with existing pandas workflows
        - Performance: Zero-copy conversion (DuckDB → Arrow → pandas)

        Example:
            >>> df = engine.query_to_df("SELECT route, AVG(avg_flow) FROM traffic_data GROUP BY route")
            >>> df.plot(x='route', y='avg_flow', kind='bar')
        """
        return self.execute(sql, params).df()

    def close(self):
        """
        Close database connection.

        Industry Practice:
        - Context manager pattern: Use with statement
        - Resource cleanup: Prevent connection leaks
        - Similar to: file.close(), connection.close()

        Example:
            >>> engine = DuckDBQueryEngine()
            >>> try:
            >>>     df = engine.query_to_df("SELECT * FROM traffic_data LIMIT 10")
            >>> finally:
            >>>     engine.close()  # Always cleanup
        """
        if self.db:
            self.db.close()
            logger.info("✅ DuckDB connection closed")

    def __enter__(self):
        """Context manager entry (支援 with 語法)"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit (自動清理)"""
        self.close()

    def cache_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics.

        Returns cache metrics including hit rate, size, and total queries.
        Useful for monitoring and optimization.

        Returns:
            dict: Cache statistics (see QueryCache.get_stats() for details)

        Industry Practice:
        - Monitoring: Export to Prometheus, Grafana, DataDog
        - SLO Target: >50% cache hit rate for dashboard workloads
        - Alerting: Alert if hit rate drops significantly

        Example:
            >>> stats = engine.cache_stats()
            >>> print(f"Cache hit rate: {stats['cache_hit_rate']:.1%}")
            >>> print(f"Cache usage: {stats['cache_size']}/{stats['cache_max_size']}")
            >>>
            >>> # Check if cache is effective
            >>> if stats['cache_hit_rate'] < 0.3:
            >>>     print("⚠️  Low cache hit rate, consider increasing cache size")
        """
        return self.cache.get_stats()

    def clear_cache(self):
        """
        Clear all cached query results.

        Use Cases:
        - After data refresh (new Parquet files uploaded)
        - Memory pressure (free up RAM)
        - Testing (ensure fresh queries)
        - Manual cache invalidation

        Industry Practice:
        - Similar to: Redis FLUSHDB, browser clear cache
        - When to use: After ETL runs, data updates, deployments

        Example:
            >>> # After processing new data
            >>> processor.process_new_data()
            >>> engine.clear_cache()  # Invalidate stale cached results
            >>> print("Cache cleared, next queries will fetch fresh data")
        """
        self.cache.clear()

    # ========================================
    # Traffic-Specific Query Methods
    # (Domain-Specific API for common queries)
    # ========================================

    def query_traffic_by_route(
        self,
        route: int,
        direction: Optional[str] = None,
        year: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Query traffic data by route with optional filters.

        This is a high-level API that abstracts SQL complexity for common route queries.

        Args:
            route: Route number as integer (e.g., 5 for I-5, 405 for I-405, 91 for SR-91)
            direction: Optional direction filter ("N", "S", "E", "W")
            year: Optional year filter (e.g., 2024)

        Returns:
            pd.DataFrame: Traffic data matching the filters, sorted by time

        Industry Practice:
        - Similar to: Django ORM .filter(), SQLAlchemy .query()
        - Query Builder Pattern: Dynamically construct SQL based on parameters
        - Prevents SQL injection: Uses parameterized queries

        Performance:
        - DuckDB pushes predicates down to Parquet (only reads matching rows)
        - Column pruning: Only loads needed columns
        - Typical query time: 50-200ms for single route/year

        Example:
            >>> # Get all I-5 northbound traffic in 2024
            >>> df = engine.query_traffic_by_route(route=5, direction="N", year=2024)
            >>> print(f"Found {len(df):,} records")

            >>> # Get all I-405 traffic (all directions, all years)
            >>> df = engine.query_traffic_by_route(route=405)
        """
        # Build dynamic WHERE clause based on provided parameters
        # Industry note: Similar to query builders in Laravel, Knex.js
        conditions = ["route = ?"]
        params = [route]

        if direction:
            conditions.append("direction = ?")
            params.append(direction)

        if year:
            conditions.append("year = ?")
            params.append(year)

        where_clause = " AND ".join(conditions)

        # Construct SQL query
        # Note: Only select commonly used columns (not all 50+ raw columns)
        sql = f"""
            SELECT
                station,
                route,
                direction,
                hour,
                month,
                year,
                avg_flow,
                median_flow,
                avg_speed,
                median_speed,
                avg_occup,
                lanes,
                days_observed
            FROM traffic_data
            WHERE {where_clause}
            ORDER BY year, month, hour
        """

        logger.info(
            f"Querying traffic data: route={route}, direction={direction}, year={year}"
        )

        try:
            result = self.execute(sql, params).df()
            logger.info(f"✅ Query returned {len(result):,} rows")
            return result
        except Exception as e:
            logger.error(f"❌ Query failed: {e}")
            raise

    def query_hourly_patterns(
        self, route: int, months: List[str], year: int = 2024
    ) -> pd.DataFrame:
        """
        Analyze hourly traffic patterns for specific months.

        Aggregates traffic data by hour to identify peak periods and trends.
        Useful for understanding daily traffic cycles.

        Args:
            route: Route number as integer (e.g., 5 for I-5, 405 for I-405)
            months: List of month names (e.g., ["January", "February", "March"])
            year: Year to analyze (default: 2024)

        Returns:
            pd.DataFrame: Hourly aggregated statistics with columns:
                - hour: Hour of day (0-23)
                - avg_flow: Average flow across all days
                - median_speed: Median speed across all days
                - months_covered: Number of months with data

        Industry Practice:
        - Time-series aggregation: Similar to Google Analytics hourly metrics
        - OLAP query: Uses GROUP BY + aggregation functions
        - Window analysis: Can extend to rolling averages, percentiles

        Performance:
        - Pre-aggregates data (reduces memory usage)
        - DuckDB's columnar storage optimized for aggregations
        - Typical query time: 100-500ms

        Use Cases:
        - Dashboard: Show daily traffic pattern chart
        - Reporting: Identify rush hour periods
        - Forecasting: Base model for time-of-day predictions

        Example:
            >>> # Analyze I-405 morning commute patterns in Q1
            >>> df = engine.query_hourly_patterns(
            ...     route=405,
            ...     months=["January", "February", "March"],
            ...     year=2024
            ... )
            >>> # Plot results
            >>> df.plot(x='hour', y='avg_flow', kind='line')
            >>> # Find peak hour
            >>> peak_hour = df.loc[df['avg_flow'].idxmax(), 'hour']
            >>> print(f"Peak traffic at hour: {peak_hour}")
        """
        # Convert month list to SQL-friendly format
        # Industry note: Always use parameterized queries, but IN clause needs special handling
        months_str = ",".join([f"'{month}'" for month in months])

        sql = f"""
            SELECT
                hour,
                AVG(avg_flow) as avg_flow,
                MEDIAN(avg_speed) as median_speed,
                COUNT(DISTINCT month) as months_covered
            FROM traffic_data
            WHERE route = ?
              AND year = ?
              AND month IN ({months_str})
            GROUP BY hour
            ORDER BY hour
        """

        logger.info(
            f"Analyzing hourly patterns: route={route}, year={year}, months={len(months)}"
        )

        try:
            result = self.execute(sql, [route, year]).df()
            logger.info(f"✅ Generated hourly pattern for {len(result)} hours")
            return result
        except Exception as e:
            logger.error(f"❌ Hourly pattern query failed: {e}")
            raise

    def get_kpi_summary(self, year: int = 2024) -> dict:
        """
        Get key performance indicators (KPIs) for dashboard.

        Returns aggregate statistics for a given year, useful for dashboard
        summary cards and high-level monitoring.

        Args:
            year: Year to summarize (default: 2024)

        Returns:
            dict: KPI metrics including:
                - total_routes: Number of unique routes
                - total_stations: Number of unique monitoring stations
                - avg_flow_overall: Average traffic flow (vehicles/hour)
                - avg_speed_overall: Average speed (mph)
                - total_observations: Total number of data points

        Industry Practice:
        - Metrics Dashboard: Similar to Datadog, Grafana summary panels
        - Single query optimization: Fetch all KPIs in one roundtrip
        - Cache-friendly: Results stable for 5-10 minutes

        Performance:
        - Aggregates entire year's data (~100k-1M rows)
        - Columnar storage: Fast COUNT DISTINCT operations
        - Typical query time: 200-1000ms (depends on year's data volume)
        - Recommended: Cache result for 5-10 minutes

        Use Cases:
        - Dashboard homepage: "System Health" summary
        - API endpoint: /api/v1/kpi/summary?year=2024
        - Monitoring: Alert if metrics deviate from baseline

        Example:
            >>> kpi = engine.get_kpi_summary(2024)
            >>> print(f"Routes monitored: {kpi['total_routes']}")
            >>> print(f"Average flow: {kpi['avg_flow_overall']:.1f} veh/h")
            >>> print(f"Average speed: {kpi['avg_speed_overall']:.1f} mph")

            >>> # Use in Streamlit dashboard
            >>> st.metric("Total Routes", kpi['total_routes'])
            >>> st.metric("Avg Flow", f"{kpi['avg_flow_overall']:.0f} veh/h")
        """
        sql = """
            SELECT
                COUNT(DISTINCT route) as total_routes,
                COUNT(DISTINCT station) as total_stations,
                AVG(avg_flow) as avg_flow_overall,
                AVG(avg_speed) as avg_speed_overall,
                SUM(days_observed) as total_observations
            FROM traffic_data
            WHERE year = ?
        """

        logger.info(f"Fetching KPI summary for year {year}")

        try:
            result = self.execute(sql, [year]).df()

            # Convert to dict (single row result)
            # Industry note: More API-friendly than DataFrame
            kpi_dict = result.iloc[0].to_dict()

            logger.info(
                f"✅ KPI summary: {kpi_dict['total_routes']} routes, "
                f"{kpi_dict['total_stations']} stations"
            )

            return kpi_dict
        except Exception as e:
            logger.error(f"❌ KPI summary query failed: {e}")
            raise
