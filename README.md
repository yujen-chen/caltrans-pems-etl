# CalTrans PeMS ETL

A modern ETL pipeline for extracting and processing traffic data from CalTrans Performance Measurement System (PeMS). This project is adapted from [Seb-Good/caltrans-pems](https://github.com/Seb-Good/caltrans-pems).

## Features

- 🚗 **Automated Data Download**: Download hourly traffic data from PeMS with resume capability
- 📊 **Data Processing**: Clean, aggregate, and transform raw data into analysis-ready Parquet files
- ☁️ **Cloud Storage**: Automatic upload to Cloudflare R2 with smart retention policies
- 🦆 **High-Performance Queries**: DuckDB integration for 10-100x faster analytics
- 📈 **Interactive Dashboard**: Streamlit-based visualization with route and time analysis
- 🔄 **Intelligent Caching**: LRU cache for frequently-accessed queries

## Installation

```bash
# Create virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e .
```

## Quick Start

### 1. Download Traffic Data

```bash
# Set credentials (create config/credentials.env)
export PEMS_USERNAME="your_username"
export PEMS_PASSWORD="your_password"

# Download data
uv run monthly-download
```

### 2. Process Raw Data

```bash
# Process downloaded files into Parquet format
uv run python scripts/data_processor.py
```

### 3. Query Data with DuckDB

```bash
# Interactive data exploration
uv run query-data --explore

# Query specific route
uv run query-data --route 405 --direction N --limit 100

# Performance benchmark
uv run query-data --benchmark

# Export to CSV
uv run query-data --route 5 --output csv > i5_data.csv
```

### 4. Launch Dashboard

```bash
uv run streamlit run scripts/dashboard.py --server.address 0.0.0.0 --server.port 8501
```

## Usage Examples

### Python API

```python
from src.pems.core.handler import PeMSHandler
from src.pems.query import DuckDBQueryEngine

# Download data
handler = PeMSHandler(username="user", password="pass")
handler.download_files(
    start_year=2024,
    end_year=2024,
    districts=["12"],
    file_types=["station_hour"],
    months=["January", "February"]
)

# Query with DuckDB (10-100x faster than pandas)
engine = DuckDBQueryEngine(data_source="local")

# Get route data
df = engine.query_traffic_by_route(route="405", direction="N")

# Analyze hourly patterns
hourly = engine.query_hourly_patterns(
    route="5",
    months=["January", "February", "March"]
)

# Get KPI summary
kpi = engine.get_kpi_summary()
print(f"Total Routes: {kpi['total_routes']}")
print(f"Avg Flow: {kpi['avg_flow_overall']:.1f} veh/hr")
```

### Command Line Interface

```bash
# Show data summary
uv run query-data --summary

# Query with filters
uv run query-data --route 10 --direction E --month January --limit 50

# Custom SQL query
uv run query-data --sql "SELECT route, AVG(avg_flow) FROM traffic_data GROUP BY route"

# Export to JSON
uv run query-data --route 405 --output json > route_405.json
```

## Configuration

### Environment Variables

Create `config/credentials.env`:

```bash
# PeMS Credentials
PEMS_USERNAME=your_username
PEMS_PASSWORD=your_password

# R2 Storage (Optional - for cloud backup)
R2_ENDPOINT=https://account_id.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your_access_key_id
R2_SECRET_ACCESS_KEY=your_secret_access_key
R2_BUCKET=pems-processed
R2_UPLOAD_ENABLED=true

# Storage Strategy
R2_UPLOAD_RAW=true              # Upload raw files (rolling backup)
R2_RAW_ROLLING_MONTHS=12        # Keep last 12 months of raw data
R2_LOCAL_RAW_RETENTION_DAYS=30  # Delete local raw after 30 days

# DuckDB Settings
DUCKDB_PATH=:memory:            # Use in-memory database
DUCKDB_THREADS=4                # Number of threads for queries
DUCKDB_MEMORY_LIMIT=2GB         # Memory limit for DuckDB
```

## Project Structure

```
caltrans-pems-etl/
├── src/pems/
│   ├── core/
│   │   └── handler.py          # PeMS data download handler
│   ├── storage.py              # R2 cloud storage integration
│   └── query.py                # DuckDB query engine
├── scripts/
│   ├── monthly_download.py     # Automated monthly download
│   ├── data_processor.py       # Raw data processing
│   ├── query_data.py           # CLI query tool
│   ├── dashboard.py            # Streamlit dashboard
│   └── test_duckdb.py          # DuckDB engine tests
├── config/
│   └── settings.py             # Configuration and paths
├── data/
│   ├── raw/                    # Raw traffic data files
│   ├── processed/              # Processed Parquet files
│   ├── meta/                   # Station metadata
│   └── exports/                # Exported analysis results
└── tests/                      # Unit and integration tests
```

## Performance

DuckDB integration provides significant performance improvements:

| Operation | Pandas | DuckDB | Speedup |
|-----------|--------|--------|---------|
| Large file read | 5-10s | 0.5-1s | **10x** |
| Complex aggregation | 30-60s | 1-3s | **20x** |
| Multi-file join | 60s+ | 2-5s | **30x** |
| Cached queries | 5-10s | 0.1s | **100x** |

## Data Coverage

Current processed data (as of 2025-10):
- **Years**: 2019-2025 (7 years)
- **Records**: 2.2M+ observations
- **Routes**: 14 major routes
- **Stations**: 1,723 traffic sensors
- **Size**: 95 MB (processed Parquet)

## Dashboard Features

- 🗺️ **Route Selection**: Up to 3 routes simultaneously
- 📊 **Multi-year Comparison**: Compare traffic patterns across years
- 🕐 **Hourly Analysis**: Speed and flow by hour of day
- 📍 **Lane Type Filter**: Mainline (ML) vs HOV lanes
- 🧭 **Direction Filter**: Northbound/Southbound or Eastbound/Westbound
- 📈 **Two-way Analysis**: Combined directional traffic totals

## Development

### Run Tests

```bash
# Run all tests
uv run pytest

# Test DuckDB engine
uv run python scripts/test_duckdb.py

# Code formatting
uv run black .

# Linting
uv run flake8 .
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Troubleshooting

### DuckDB Import Error
```bash
# Install DuckDB if missing
uv pip install duckdb>=1.0.0
```

### R2 Connection Failed
- Verify R2 credentials in `config/credentials.env`
- Check endpoint URL format (must include `https://`)
- Ensure bucket exists and has correct permissions

### Empty Query Results
- Verify processed data exists in `data/processed/`
- Run `uv run query-data --summary` to check available data
- Check route names match data (use integers: 5, 405, not I-5)

## License

MIT License

## Acknowledgments

- Original project: [Seb-Good/caltrans-pems](https://github.com/Seb-Good/caltrans-pems)
- Data source: [California PeMS](http://pems.dot.ca.gov)
