# Setup Guide

These steps take you from a fresh clone to a running copilot. For what the project is and why it is built this way, see [README.md](README.md).

Commands are for **Windows PowerShell**, run from the repository root.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Python **3.12** | The pinned packages in `requirements.txt` target 3.12. |
| [Microsoft ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server) | Used by `pyodbc` for every SQL connection. |
| Azure SQL Database | A server and an empty database (this guide uses `coldchain`) with a SQL admin login. |
| [Pinecone](https://www.pinecone.io/) account | The free tier is enough. The index is created automatically. |
| An LLM API key | [Groq](https://console.groq.com/) (free tier), OpenAI or DeepSeek. Alternatively, install [Ollama](https://ollama.com/) and run a local model. |
| About 3 GB of free disk space | For the local `BAAI/bge-m3` embedding model, downloaded on first run. Not needed with OpenAI embeddings. |

---

## 2. Create the virtual environment

```powershell
py -3.12 -m venv .venv312
.venv312\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The rest of this guide assumes the environment is active. Without activating it, replace `python` with `.venv312\Scripts\python.exe`.

---

## 3. Configure `.env`

Create `.env` in the **repository root**. Every script reads it from there. It is in `.gitignore`, so it is never committed.

```dotenv
# --- Azure SQL: admin (used for ingestion and the audit-log viewer) ---
AZURE_SQL_SERVER=your-server.database.windows.net
AZURE_SQL_DATABASE=coldchain
SQL_ADMIN_USER=sqladmin
SQL_ADMIN_PASSWORD=...

# --- Azure SQL: read-only agent user (used by the agent at runtime) ---
SQL_SERVER_HOST=your-server.database.windows.net
SQL_SERVER_PORT=1433
SQL_AGENT_USER=USR_FDE_RO
SQL_AGENT_PASSWORD=...          # must match the password set in step 6

# --- Vector store ---
PINECONE_API_KEY=...

# --- Embeddings: LOCAL (BAAI/bge-m3, free, on CPU) or OPENAI ---
Embeddings_model=LOCAL
Local_Embedding_Model=BAAI/bge-m3

# --- Agent LLM: GROQ, OPENAI, DEEPSEEK, or anything else for local Ollama ---
Agent_llm=GROQ
GROQ_API_KEY=gsk_...
Groq_model=openai/gpt-oss-120b
# OPENAI_API_KEY=sk-...          # needed for Agent_llm=OPENAI or Embeddings_model=OPENAI
# DEEPSEEK_API_KEY=sk-...        # needed for Agent_llm=DEEPSEEK
```

`data-ingestion/.env.example` lists only the four admin SQL settings. Use the block above for the full set.

**Notes**
- Server values are the host name only, without `tcp:` or a port.
- If you change `Embeddings_model`, run step 7 again. Each embedding model has its own Pinecone index.
- Groq retires models from time to time. If you get `model_not_found`, list the models available to your key:
  ```powershell
  curl.exe -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $env:GROQ_API_KEY"
  ```
  Then pick one that supports tool calling.

---

## 4. Allow your IP through the Azure SQL firewall

Azure SQL rejects connections from IP addresses that aren't on its allow list. Use either option:

- **Portal:** SQL server → *Security → Networking* → **Add your client IPv4 address** → Save.
- **SQL:** connected to the `master` database as the admin, run:
  ```sql
  EXEC sp_set_firewall_rule N'dev-machine', '<your-ip>', '<your-ip>';
  ```

If your home IP changes, you'll get `Client with IP address '...' is not allowed to access the server` again. Repeat this step with the new IP.

---

## 5. Load the legacy fleet data

```powershell
python data-ingestion\scripts\ingest_to_azure_sql.py
```

This writes 32,065 rows to `dbo.TBL_SC_FLEET_HIST_RAW`. **It drops and recreates the table on every run.** For details and troubleshooting, see [data-ingestion/db-ingestion-instructions.md](data-ingestion/db-ingestion-instructions.md).

---

## 6. Create the semantic view, agent user and audit table

Connect to the **app database** (`coldchain`, **not** `master`) as the admin user. You can use the VS Code MSSQL extension, Azure Data Studio, SSMS or the portal query editor.

### 6a. View and read-only user

Before running it, open [data-ingestion/scripts/setup_security_and_view.sql](data-ingestion/scripts/setup_security_and_view.sql) and **change the password** in section 3 to the value of `SQL_AGENT_PASSWORD` in your `.env`. Then run the whole file.

It creates:
- the `FDE_VIEWS` schema and the `FDE_VIEWS.VW_ACTIVE_FLEET` view;
- the contained database user `USR_FDE_RO`;
- `SELECT` permission on the view only, with access to the raw table denied and writes to `dbo` denied.

The `CREATE SCHEMA` and `CREATE VIEW` statements are not safe to run twice. If they already exist, run only from section 3 down.

### 6b. Audit log table

The UI writes agent traces to this table. Run:

```sql
CREATE TABLE FDE_VIEWS.AgentAuditLog (
    LogID        INT IDENTITY(1,1) PRIMARY KEY,
    [Timestamp]  DATETIME2 DEFAULT SYSUTCDATETIME(),
    SessionID    VARCHAR(50),
    NodeExecuted VARCHAR(50),
    ToolName     VARCHAR(100),
    Content      NVARCHAR(MAX)  -- NVARCHAR to safely handle JSON strings and large LLM outputs
);
GO

GRANT INSERT ON FDE_VIEWS.AgentAuditLog TO USR_FDE_RO;
GO
```

### 6c. Verify

```sql
SELECT TOP 5 * FROM FDE_VIEWS.VW_ACTIVE_FLEET;
SELECT name, type_desc FROM sys.database_principals WHERE name = 'USR_FDE_RO';
```

---

## 7. Index the SOP into Pinecone

```powershell
python data-ingestion\scripts\ingest_sop_pinecone.py
```

- Reads every `.md`, `.txt`, `.pdf`, `.csv` and `.xlsx` file in [policy/](policy/).
- Creates the Pinecone index on the first run: `fde-sop-index-local` (1024 dimensions), or `fde-sop-index-openai` (1536 dimensions) with OpenAI embeddings.
- With `LOCAL` embeddings, the first run downloads `BAAI/bge-m3`, about 2.3 GB, which takes a few minutes.
- Re-runs are incremental: unchanged files print `Skipped (Unchanged)`. To force a full re-index, delete `data/cache/ingestion_hash_cache.json`.

Expected output for the bundled SOP:

```
Found 1 policy file(s) in ...\policy...
🔄 Processing updates: Cold_Chain_Incident_SOP_v2.md...
  📤 Upserting 4 chunk(s) in batches of 100...
✅ Ingestion & cache update complete.
```

---

## 8. Smoke-test the tools

```powershell
python src\agent_tools.py
```

Each of the three tools should return data:
- **Tool 1** returns 2 rows from `VW_ACTIVE_FLEET`. This confirms the read-only user, the firewall rule and the view.
- **Tool 2** returns current weather for Long Beach. This confirms internet access.
- **Tool 3** returns SOP sections. This confirms Pinecone and the embeddings.

Fix any failure here before you start the agent. See [Troubleshooting](#troubleshooting).

---

## 9. Run the copilot

### Web UI (recommended)

```powershell
python -m streamlit run src\ui.py
```

Open http://localhost:8501.
- **🧊 Dispatch Console:** ask questions. Expand the tool panels to see the generated SQL and the raw results.
- **🛡️ Security & Audit Logs:** enter the `SQL_ADMIN_USER` / `SQL_ADMIN_PASSWORD` credentials to view the audit trail.

### Terminal chat

```powershell
python src\orchestrator.py
```

Type questions at `Dispatcher >`, and type `exit` to quit.

### Example questions

- *Show me shipments near Los Angeles and tell me which ones breach the SOP and what to do.*
- *Which High Risk shipments need to be escalated to the Tier 2 Logistics Manager?*
- *What does the SOP say about port congestion at Long Beach?*
- *What's the difference between Tier 1 and Tier 2 escalation?* The correct answer is that the SOP doesn't define Tier 1.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `Missing PINECONE_API_KEY in .env` | `.env` is not in the repo root, or the key is missing | Put `.env` at the repo root (step 3). |
| `Client with IP address '...' is not allowed to access the server` (40615) | Firewall | Step 4. |
| `Login failed for user 'USR_FDE_RO'` (18456) | The connection targets `master`, or the password doesn't match | `AZURE_SQL_DATABASE` must name the app database; `SQL_AGENT_PASSWORD` must match the password set in step 6a. |
| `User must be in the master database` (5001) | `CREATE LOGIN` run against Azure SQL | Use the contained-user version of `setup_security_and_view.sql` (`CREATE USER ... WITH PASSWORD`). |
| `Invalid object name 'FDE_VIEWS.VW_ACTIVE_FLEET'` | Wrong database, or a typo (for example `VM_` instead of `VW_`) | Connect to the app database and check the name. |
| `Could not find stored procedure '...'` | Only part of the script was highlighted when you pressed Run | Select the full statement block, or clear the selection to run the whole file. |
| `Audit Log Failed (Silent): ...` in the terminal | The audit table is missing, or `INSERT` wasn't granted | Step 6b. |
| `Error code: 402 - Insufficient Balance` | The LLM provider account is out of credit | Top up, or switch `Agent_llm` (for example to `GROQ`). |
| `model_not_found` (404) from Groq | The model was retired, or your key can't use it | List the available models (step 3 notes) and set `Groq_model`. |
| `429` rate-limit errors | Free-tier per-minute limits; each question makes several LLM calls | Wait a minute between questions, or use a paid tier. |
| Answer cut off mid-sentence | `max_tokens` exhausted (reasoning models count hidden reasoning tokens) | Raise `max_tokens` in [src/orchestrator.py](src/orchestrator.py). |
| `No matching compliance clauses found.` | The index is empty, or the wrong index for the current embedding setting | Run step 7 again with the same `Embeddings_model`. |
| `You are sending unauthenticated requests to the HF Hub` | Informational only | Optionally set `HF_TOKEN` for faster downloads. |
