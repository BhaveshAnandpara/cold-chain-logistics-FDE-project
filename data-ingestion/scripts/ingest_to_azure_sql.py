"""Load the raw supply chain CSV into Azure SQL Database.

Usage:
    .venv\\Scripts\\python data-ingestion\\scripts\\ingest_to_azure_sql.py

Reads connection settings from .env (see .env.example). The target table is
dropped and recreated on every run, so the script is safe to re-run.
"""

import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

INGESTION_DIR = Path(__file__).resolve().parent.parent
ROOT = INGESTION_DIR.parent
CSV_PATH = INGESTION_DIR / "data" / "raw" / "dynamic_supply_chain_logistics_dataset.csv"
TABLE = "dbo.supply_chain_logistics"
DRIVER = "ODBC Driver 18 for SQL Server"
BATCH_SIZE = 5000

TEXT_COLUMNS = {"risk_classification": "VARCHAR(20)"}
TIMESTAMP_COLUMN = "timestamp"


def connect() -> pyodbc.Connection:
    load_dotenv(ROOT / ".env")
    missing = [k for k in ("AZURE_SQL_SERVER", "AZURE_SQL_DATABASE", "AZURE_SQL_USER", "AZURE_SQL_PASSWORD") if not os.getenv(k)]
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

    # A serverless database that auto-paused takes up to ~1 minute to resume,
    # and connections fail with error 40613 while it wakes up. Anything else
    # (firewall, bad password) won't fix itself, so fail fast on those.
    for attempt in range(1, 6):
        try:
            return pyodbc.connect(conn_str)
        except pyodbc.Error as exc:
            message = str(exc)
            if "(40615)" in message:
                sys.exit("Blocked by the Azure SQL firewall. Add your current IP under "
                         "SQL server -> Security -> Networking -> Firewall rules.\n" + message)
            if "(18456)" in message:
                sys.exit("Login failed. Check AZURE_SQL_USER / AZURE_SQL_PASSWORD in .env.")
            if "(40613)" not in message or attempt == 5:
                raise
            print(f"Attempt {attempt}: database is resuming from auto-pause, retrying in 15s...")
            time.sleep(15)


def column_type(name: str) -> str:
    if name == TIMESTAMP_COLUMN:
        return "DATETIME2(0) NOT NULL"
    return f"{TEXT_COLUMNS.get(name, 'FLOAT')} NOT NULL"


def parse_row(header: list[str], row: list[str]) -> list:
    values = []
    for name, raw in zip(header, row):
        if name == TIMESTAMP_COLUMN:
            values.append(datetime.strptime(raw, "%Y-%m-%d %H:%M:%S"))
        elif name in TEXT_COLUMNS:
            values.append(raw)
        else:
            values.append(float(raw))
    return values


def main() -> None:
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [parse_row(header, r) for r in reader]
    print(f"Read {len(rows):,} rows x {len(header)} columns from {CSV_PATH.name}")

    conn = connect()
    cursor = conn.cursor()
    cursor.fast_executemany = True

    column_defs = ",\n    ".join(f"[{c}] {column_type(c)}" for c in header)
    cursor.execute(f"DROP TABLE IF EXISTS {TABLE};")
    cursor.execute(
        f"CREATE TABLE {TABLE} (\n"
        f"    id INT IDENTITY(1,1) PRIMARY KEY,\n"
        f"    {column_defs}\n"
        f");"
    )

    insert_sql = (
        f"INSERT INTO {TABLE} ({', '.join(f'[{c}]' for c in header)}) "
        f"VALUES ({', '.join('?' for _ in header)})"
    )
    for start in range(0, len(rows), BATCH_SIZE):
        cursor.executemany(insert_sql, rows[start:start + BATCH_SIZE])
        print(f"  inserted {min(start + BATCH_SIZE, len(rows)):,} / {len(rows):,}")
    conn.commit()

    count = cursor.execute(f"SELECT COUNT(*) FROM {TABLE};").fetchone()[0]
    conn.close()
    if count != len(rows):
        sys.exit(f"Row count mismatch: CSV has {len(rows):,}, table has {count:,}")
    print(f"Done. {TABLE} now has {count:,} rows.")


if __name__ == "__main__":
    main()
