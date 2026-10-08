# Azure SQL Ingestion Instructions

This guide explains how to load the supply chain CSV into Azure SQL using `data-ingestion/scripts/ingest_to_azure_sql.py`.

## What the script does

- Reads `data-ingestion/data/raw/dynamic_supply_chain_logistics_dataset.csv`.
- Keeps the tutorial's legacy schema: it selects 9 CSV columns, renames them, and adds `SYS_INGEST_FLAG = 'Y'`.
- Creates `dbo.TBL_SC_FLEET_HIST_RAW` in the Azure SQL database configured by `AZURE_SQL_DATABASE`.
- Writes rows in chunks of 5,000 and checks the final SQL row count against the transformed DataFrame.
- Replaces the destination table on every run. **The script drops and recreates `dbo.TBL_SC_FLEET_HIST_RAW`**, so back up any data you need before running it. It does not append to the table.

## Prerequisites

- Windows with Python installed.
- Microsoft ODBC Driver 18 for SQL Server installed.
- Network access to the Azure SQL server. The machine's current public IP must be allowed by the server firewall.
- Azure SQL credentials with permission to drop and create tables and insert rows in the target database.

The tutorial targets a local Docker SQL Server and uses `master`; this version targets your Azure SQL database (`coldchain` in the example `.env`) and keeps encryption enabled.

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
py -3.12 -m venv .venv312
.venv312\Scripts\Activate.ps1
python -m pip install -r data-ingestion\requirements.txt
python data-ingestion\scripts\ingest_to_azure_sql.py
```

If `.venv312` already exists, activate it and install/update dependencies with the last two setup commands. The script can also be run without activating the environment using:

```powershell
.venv312\Scripts\python data-ingestion\scripts\ingest_to_azure_sql.py
```

On success, the script prints the number of CSV rows and columns read, batch insertion progress, and a final confirmation with the SQL table's row count.

## Verify the load

Connect to the database named by `AZURE_SQL_DATABASE` and run:

```sql
SELECT COUNT(*) AS row_count
FROM dbo.TBL_SC_FLEET_HIST_RAW;

SELECT TOP (10) *
FROM dbo.TBL_SC_FLEET_HIST_RAW;
```

The row count should match the number reported by the script. The table columns are `TS_UTC`, `V_LAT`, `V_LON`, `IOT_TEMP_VAL_C`, `CGO_COND_CD`, `RISK_CLS_TXT`, `DELAY_PROB_DEC`, `PRT_CNG_LVL`, `RT_RSK_IDX`, and `SYS_INGEST_FLAG`.

## Troubleshooting

- **Missing in `.env`:** Check that all four `AZURE_SQL_*` values are present and that `.env` is in the repository root.
- **ODBC Driver 18 is not installed:** Install the Microsoft ODBC Driver 18 for SQL Server, then rerun the script.
- **Firewall error `(40615)`:** Add the machine's current public IP to the Azure SQL server firewall rules and retry.
- **Login error `(18456)`:** Verify the SQL username, password, and database access in `.env`.
- **Database resuming error `(40613)`:** The script retries automatically while a serverless database resumes. If retries are exhausted, rerun once the database is available.
- **Table permission or insert errors:** Ensure the login can replace `dbo.TBL_SC_FLEET_HIST_RAW` and insert rows in the selected database.
- **CSV file not found:** Confirm the file is at `data-ingestion/data/raw/dynamic_supply_chain_logistics_dataset.csv`; the script uses this fixed path.