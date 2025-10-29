import pytest
from src.pems.query import DuckDBQueryEngine, QueryCache


class TestQueryCache:
    """
    Test suite for QueryCache functionality

    This test class validates the QueryCache implementation used in the DuckDBQueryEngine
    for query result caching. The QueryCache provides LRU (Least Recently Used) caching
    with TTL (Time To Live) expiration to optimize repeated query performance.

    Test Coverage:
    - Cache initialization with custom and default parameters
    - Setting and getting cached query results
    - Cache hit scenarios (successful retrieval from cache)
    - Cache miss scenarios (non-existent keys return None)
    - Cache statistics tracking (hit_count, miss_count, hit_rate)

    Dependencies:
    - pandas: For creating test DataFrame objects
    - QueryCache class: Located in src/pems/query module

    Example Usage:
        # Run all tests
        pytest tests/test_query_cache.py -v

        # Run specific test
        pytest tests/test_query_cache.py::TestQueryCache::test_cache_set_and_get -v
    """

    def test_cache_initialization(self):
        """
        from query.py:
        def __init__(self, max_size: int = 100, ttl: int = 300):
            self.cache = OrderedDict()
            self.max_size = max_size
            self.ttl = ttl
            self.timestamps = {}
            self.hit_count = 0
            self.miss_count = 0
            logger.info(f"✅ QueryCache initialized (max_size={max_size}, ttl={ttl}s)")
        """
        # Arrange
        # testing params
        test_max_size = 50
        test_ttl = 600

        # Act
        # create QueryCache instance
        test_cache = QueryCache(max_size=test_max_size, ttl=test_ttl)

        # Assert
        # assert max_size and ttl
        assert (
            test_cache.max_size == test_max_size
        ), f"max_size should be {test_max_size}"
        assert test_cache.ttl == test_ttl, f"ttl should be {test_ttl}"

        from collections import OrderedDict

        # assert test_cache is an OrderedDict class
        assert isinstance(
            test_cache.cache, OrderedDict
        ), "cache should be OrderedDict class"

        # assert test_cache is empty
        assert len(test_cache.cache) == 0, "initial cache should be empty"

        # assert timestamp is a dict and empty
        assert isinstance(test_cache.timestamps, dict), "timestamp should be dict type"
        assert len(test_cache.timestamps) == 0, "timestamp should be empty"

        # assert hit_count and miss_count
        assert test_cache.hit_count == 0, "hit_count should be 0"
        assert test_cache.miss_count == 0, "miss_count should be 0"

    def test_cache_initialization_with_defaults(self):
        """
        Test QueryCache class with default values
        """

        test_cache = QueryCache()

        # assert default values for max_size and ttl
        assert test_cache.max_size == 100, "default max_size should be 100"
        assert test_cache.ttl == 300, "default ttl should be 300"

    def test_cache_set_and_get(self):

        # === Arrange ===
        test_cache = QueryCache(max_size=3, ttl=300)

        test_sql = f"""
                SELECT * 
                FROM traffic_data 
                WHERE year = ?
                AND route = ?
                LIMIT 10
        """
        test_params = [2023, 91]
        test_data_source = "local"

        import pandas as pd

        test_result = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "year": [2021, 2022, 2023],
                "route": [5, 405, 91],
                "flow": [100, 200, 300],
            }
        )

        # === Act ===
        test_cache.set(
            sql=test_sql,
            params=test_params,
            data_source=test_data_source,
            result=test_result,
        )
        result = test_cache.get(sql=test_sql, params=test_params, data_source="local")

        # === Assert ===
        # assert the result is not None
        assert result is not None, "result should be retrieved from cache"
        # assert the output result from get equals to result input by set
        assert result.equals(
            test_result
        ), "result should be the same as the input df by set"
        # assert cache stats
        test_stats = test_cache.get_stats()
        assert test_stats["total_queries"] == 1, "total queries should be 1"
        assert test_stats["cache_hits"] == 1, "cache hits should be 1"
        assert test_stats["cache_misses"] == 0, "total queries should be 0"
        assert test_stats["cache_hit_rate"] == 1, "total hit rate should be 1"
        assert test_stats["cache_size"] == 1, "cache size should be 1"
        assert test_stats["cache_max_size"] == 3, "cache max size should be 3"

    def test_cache_miss(self):
        """
        Querying a non-existent item should return None
        """
        # === Arrange ===
        test_cache = QueryCache()

        test_sql = f"""
                SELECT * FROM traffic_data
                WHERE year = ?
                AND route = ?
                LIMIT 5
        """
        test_params_1 = [2021, 5]
        test_params_2 = [2022, 22]
        test_data_source = "local"

        import pandas as pd

        test_result = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "year": [2021, 2022, 2023],
                "route": [5, 405, 91],
                "flow": [100, 200, 300],
            }
        )

        # === Act ===
        test_cache.set(
            sql=test_sql,
            params=test_params_1,
            data_source=test_data_source,
            result=test_result,
        )

        result = test_cache.get(
            sql=test_sql,
            params=test_params_2,
            data_source=test_data_source,
        )

        # === Assert ===
        assert result is None, "The result should be none"

        test_stats = test_cache.get_stats()
        assert test_stats["total_queries"] == 1, "total queries should be 1"
        assert test_stats["cache_hits"] == 0, "cache hits should be 0"
        assert test_stats["cache_misses"] == 1, "miss queries should be 1"
        assert test_stats["cache_hit_rate"] == 0, "total hit rate should be 0"
        assert test_stats["cache_size"] == 1, "cache size should be 1"

    def test_cache_hit_updates_lru_order(self):
        """
        When Cache hit, the item should move to end

        Test Strategy:
        1. Insert 3 items with different keys: A, B, C (order: A -> B -> C)
        2. Access A (via get), which should move A to end (order: B -> C -> A)
        3. Verify last key is A
        """

        # === Arrange ===
        test_cache = QueryCache()

        test_sql = """
                SELECT * FROM traffic_data
                WHERE year = ?
                AND route = ?
                LIMIT 5
        """

        # Three different parameter sets to generate different keys
        test_params_A = [2021, 91]  # First item (will be accessed later)
        test_params_B = [2022, 5]  # Second item
        test_params_C = [2023, 405]  # Third item
        test_data_source = "local"

        import pandas as pd

        test_result = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "year": [2021, 2022, 2023],
                "route": [5, 405, 91],
                "flow": [100, 200, 300],
            }
        )

        # === Act ===
        # Step 1: Insert A, B, C (order: A -> B -> C)
        test_cache.set(
            sql=test_sql,
            params=test_params_A,
            data_source=test_data_source,
            result=test_result,
        )
        test_cache.set(
            sql=test_sql,
            params=test_params_B,
            data_source=test_data_source,
            result=test_result,
        )
        test_cache.set(
            sql=test_sql,
            params=test_params_C,
            data_source=test_data_source,
            result=test_result,
        )

        # Verify initial order: A -> B -> C (C should be last)
        initial_keys = list(test_cache.cache.keys())
        key_C = test_cache._generate_key(test_sql, test_params_C, test_data_source)
        assert initial_keys[-1] == key_C, "Initial order should have C at the end"

        # Step 2: Access A (cache hit should move A to end)
        # Order should become: B -> C -> A
        result = test_cache.get(
            sql=test_sql,
            params=test_params_A,
            data_source=test_data_source,
        )

        # Verify cache hit (not None)
        assert result is not None, "Cache hit should return the cached result"

        # === Assert ===
        # Step 3: Verify A is now at the end (most recently used)
        final_keys = list(test_cache.cache.keys())
        key_A = test_cache._generate_key(test_sql, test_params_A, test_data_source)

        assert final_keys[-1] == key_A, (
            f"After cache hit, key A should be at the end. "
            f"Expected: {key_A}, Got: {final_keys[-1]}"
        )

        # Additional verification: cache should still have 3 items
        assert len(test_cache.cache) == 3, "Cache should still have 3 items"

    def test_cache_eviction_lru(self):
        """
        remove the oldest item when the cache is full
        """

        # == Arrange ==
        test_cache = QueryCache(max_size=3, ttl=300)
        test_sql = """
                SELECT * FROM traffic_data
                WHERE year = ?
                AND route = ?
                LIMIT 5
        """

        # Three different parameter sets to generate different keys
        test_params_1 = [2021, 91]  # First item (will be accessed later)
        test_params_2 = [2022, 5]  # Second item
        test_params_3 = [2023, 405]  # Third item
        test_params_4 = [2024, 55]  # forth item
        test_data_source = "local"

        import pandas as pd

        test_result = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "year": [2021, 2022, 2023],
                "route": [5, 405, 91],
                "flow": [100, 200, 300],
            }
        )

        # === Act ===
        test_cache.set(
            sql=test_sql,
            params=test_params_1,
            data_source=test_data_source,
            result=test_result,
        )
        test_cache.set(
            sql=test_sql,
            params=test_params_2,
            data_source=test_data_source,
            result=test_result,
        )
        test_cache.set(
            sql=test_sql,
            params=test_params_3,
            data_source=test_data_source,
            result=test_result,
        )
        test_cache.set(
            sql=test_sql,
            params=test_params_4,
            data_source=test_data_source,
            result=test_result,
        )

        # === Assert ===
        # generate the key for the oldest set
        test_cache_key_1 = test_cache._generate_key(
            sql=test_sql,
            params=test_params_1,
            data_source=test_data_source,
        )

        test_cache_keys = list(test_cache.cache.keys())

        assert test_cache_key_1 not in test_cache_keys, (
            f"The oldest key (params_1) should be evicted when cache is full. "
            f"Expected key_1 NOT in cache, but found it in: {test_cache_keys}"
        )

        # Additional verification: cache should still have max_size items
        assert (
            len(test_cache.cache) == 3
        ), "Cache should have exactly 3 items (max_size)"

    def test_cache_ttl_expiration(self):
        """
        Test TTL expiration with lazy eviction strategy
        Strategy:
        1. Set TTL to 1 second
        2. Insert an item into cache
        3. Wait 2 seconds (exceed TTL)
        4. Access the item via get() to trigger TTL check - the item stay longer than ttl will be removed
        5. Verify item is removed (lazy expiration) and get() returns None
        """

        # === Arrange ===
        test_cache = QueryCache(max_size=3, ttl=1)
        test_sql = """
                SELECT * FROM traffic_data
                WHERE year = ?
                AND route = ?
                LIMIT 5
        """

        # Three different parameter sets to generate different keys
        test_params_1 = [2021, 91]  # First item (will be accessed later)

        test_data_source = "local"

        import pandas as pd
        import time

        test_result = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "year": [2021, 2022, 2023],
                "route": [5, 405, 91],
                "flow": [100, 200, 300],
            }
        )

        # === Act ===
        test_cache.set(
            sql=test_sql,
            params=test_params_1,
            data_source=test_data_source,
            result=test_result,
        )

        time.sleep(2)

        # === Assert ===
        test_result = test_cache.get(
            sql=test_sql,
            params=test_params_1,
            data_source=test_data_source,
        )

        assert len(test_cache.cache) == 0, "The cache should be empty."

    def test_cache_clear(self):
        """
        1. Store multiple items
        2. Call cache.clear()
        3. Verify the cache is empty and statistics are reset to zero
        """
        pass
