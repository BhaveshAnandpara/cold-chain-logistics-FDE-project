"""Load the supply chain CSV into the legacy fleet-history table.

Usage:
    .venv312\\Scripts\\python data-ingestion\\scripts\\ingest_to_azure_sql.py

Reads Azure SQL connection settings from the repository-root .env. The target
table is replaced on every run.
"""

import os
import sys
import urllib.parse
from pathlib import Path

import pandas as pd
import pyodbc
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

INGESTION_DIR = Path(__file__).resolve().parent.parent
ROOT = INGESTION_DIR.parent
CSV_PATH = INGESTION_DIR / "data" / "raw" / "dynamic_supply_chain_logistics_dataset.csv"
TABLE = "TBL_SC_FLEET_HIST_RAW"
DRIVER = "ODBC Driver 18 for SQL Server"
CHUNKSIZE = 5000
LEGACY_MAPPING = {
    "timestamp": "TS_UTC",
    "vehicle_gps_latitude": "V_LAT",
    "vehicle_gps_longitude": "V_LON",
    "iot_temperature": "IOT_TEMP_VAL_C",
    "cargo_condition_status": "CGO_COND_CD",
    "risk_classification": "RISK_CLS_TXT",
    "delay_probability": "DELAY_PROB_DEC",
    "port_congestion_level": "PRT_CNG_LVL",
    "route_risk_level": "RT_RSK_IDX",
}


def create_engine_for_database():
    load_dotenv(ROOT / ".env")
    required = ("AZURE_SQL_SERVER", "AZURE_SQL_DATABASE", "AZURE_SQL_USER", "AZURE_SQL_PASSWORD")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")
    if DRIVER not in pyodbc.drivers():
        sys.exit(f"'{DRIVER}' is not installed. Installed drivers: {pyodbc.drivers()}")

    conn_str = (
        f"Driver={{{DRIVER}}};"
        f"Server=tcp:{os.environ['AZURE_SQL_SERVER']},1433;"
        f"Database={os.environ['AZURE_SQL_DATABASE']};"
        f"Uid={os.environ['AZURE_SQL_USER']};"
        f"Pwd={{{os.environ['AZURE_SQL_PASSWORD']}}};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60;"
    )
    params = urllib.parse.quote_plus(conn_str)
    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={params}",
        fast_executemany=True,
        pool_pre_ping=True,
    )


def main() -> None:
    print(f"Loading CSV from {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)
    df_legacy = df[list(LEGACY_MAPPING)].rename(columns=LEGACY_MAPPING)
    df_legacy["SYS_INGEST_FLAG"] = "Y"

    print("Connecting to Azure SQL database from .env...")
    engine = create_engine_for_database()
    try:
        print(f"Ingesting {len(df_legacy):,} rows into dbo.{TABLE}...")
        df_legacy.to_sql(
            TABLE,
            engine,
            if_exists="replace",
            index=False,
            schema="dbo",
            chunksize=CHUNKSIZE,
        )

        with engine.connect() as connection:
            count = connection.execute(text(f"SELECT COUNT(*) FROM dbo.{TABLE}")).scalar_one()
    finally:
        engine.dispose()

    if count != len(df_legacy):
        sys.exit(f"Row count mismatch: CSV has {len(df_legacy):,}, table has {count:,}")
    print(f"Legacy data ingestion complete. dbo.{TABLE} now has {count:,} rows.")


if __name__ == "__main__":
    main()
