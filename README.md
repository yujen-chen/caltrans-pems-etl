# CalTrans PeMS ETL

A project for extracting and processing data from CalTrans Performance Measurement System (PeMS). This project is adapted from [Seb-Good/caltrans-pems](https://github.com/Seb-Good/caltrans-pems).

## Installation

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

## Usage

```python
from pems.handler import PeMSHandler

handler = PeMSHandler(username="your_username", password="your_password")
files = handler.get_files(start_year=2023, end_year=2023, districts=["12"], file_types=["station_hour"])
handler.download_files(start_year=2023, end_year=2023, districts=["12"], file_types=["station_hour"], months=["April", "May"])
```

## Dashboard

Run a simple Streamlit dashboard that reads yearly Parquet files under `data/processed/`:

```bash
uv run streamlit run scripts/dashboard.py --server.address 0.0.0.0 --server.port 8501
```

Notes:
- Make sure processed files exist (see `scripts/data_processor.py`).
- Use a reverse proxy (e.g., Nginx/Caddy) for HTTPS in production.

## License

MIT License
