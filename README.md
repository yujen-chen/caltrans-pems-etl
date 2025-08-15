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
files = handler.get_files(start_year=2023, end_year=2023, districts=["4"], file_types=["station_5min"])
handler.download_files(start_year=2023, end_year=2023, districts=["4"], file_types=["station_5min"], months=["01", "02"])
```

## License

MIT License
