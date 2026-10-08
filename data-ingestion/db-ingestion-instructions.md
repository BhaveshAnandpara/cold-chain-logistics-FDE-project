# Azure SQL Ingestion Instructions

This guide explains how to load the supply chain CSV into Azure SQL using `data-ingestion/scripts/ingest_to_azure_sql.py`.

## What the script does

- Reads `data-ingestion/data/raw/dynamic_supply_chain_logistics_dataset.csv`.
- Creates `dbo.supply_chain_logistics` in the configured Azure SQL database.
- Loads the CSV in batches of 5,000 rows and checks the final SQL row count against the CSV row count.
- Replaces the destination table on every run. **The script drops the existing `dbo.supply_chain_logistics` table and recreates it**, so back up any data you need before running it. It does not append to the table.

## Prerequisites

- Windows with Python installed.
- Microsoft ODBC Driver 18 for SQL Server installed.
- Network access to the Azure SQL server. The machine's current public IP must be allowed by the server firewall.
- Azure SQL credentials with permission to drop and create tables and insert rows in the target database.

## Configure the connection

From the repository root, copy `data-ingestion/.env.example` to `.env` and fill in the values for your Azure SQL server:

```powershell
Copy-Item data-ingestion\.env.example .env
```

Set these values in `.env`:

```dotenv
AZURE_SQL_SERVER=your-server.database.windows.net
AZURE_SQL_DATABASE=your-database
AZURE_SQL_USER=your-sql-login
AZURE_SQL_PASSWORD=your-sql-password
```

Do not commit `.env`; it is excluded by `.gitignore`. Keep the password private. The server value is the host name only, without `tcp:` or a port.

## Install dependencies and run

Open PowerShell in the repository root. Create and activate a virtual environment if needed, install the Python dependencies, then run the loader:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r data-ingestion\requirements.txt
python data-ingestion\scripts\ingest_to_azure_sql.py
```

If `.venv` already exists, activate it and install/update dependencies with the last two setup commands. The script can also be run without activating the environment using:

```powershell
.venv\Scripts\python data-ingestion\scripts\ingest_to_azure_sql.py
```

On success, the script prints the number of CSV rows and columns read, batch insertion progress, and a final confirmation with the SQL table's row count.

## Verify the load

Connect to the database named by `AZURE_SQL_DATABASE` and run:

```sql
SELECT COUNT(*) AS row_count
FROM dbo.supply_chain_logistics;

SELECT TOP (10) *
FROM dbo.supply_chain_logistics;
```

The row count should match the number reported by the script. The table has an identity `id` primary key in addition to the CSV columns.

## Troubleshooting

- **Missing in `.env`:** Check that all four `AZURE_SQL_*` values are present and that `.env` is in the repository root.
- **ODBC Driver 18 is not installed:** Install the Microsoft ODBC Driver 18 for SQL Server, then rerun the script.
- **Firewall error `(40615)`:** Add the machine's current public IP to the Azure SQL server firewall rules and retry.
- **Login error `(18456)`:** Verify the SQL username, password, and database access in `.env`.
- **Database resuming error `(40613)`:** The script retries automatically while a serverless database resumes. If retries are exhausted, rerun once the database is available.
- **Table permission or insert errors:** Ensure the login can drop and create `dbo.supply_chain_logistics` and insert rows in the selected database.
- **CSV file not found:** Confirm the file is at `data-ingestion/data/raw/dynamic_supply_chain_logistics_dataset.csv`; the script uses this fixed path.