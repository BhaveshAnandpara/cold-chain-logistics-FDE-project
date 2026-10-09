-- ====================================================================
-- FDE ENTERPRISE SECURITY & SEMANTIC LAYER SCRIPT
-- Purpose: Protect the legacy DB from LLM hallucinations and mutations
-- ====================================================================

-- 1. Create a dedicated schema for our clean AI views
CREATE SCHEMA FDE_VIEWS;
GO -- GO only works inside Microsoft terminal tools.

-- 2. Create the Semantic View (Translating legacy junk to clean English)
CREATE VIEW FDE_VIEWS.VW_ACTIVE_FLEET AS
SELECT 
    TS_UTC AS [Timestamp],
    V_LAT AS [Latitude],
    V_LON AS [Longitude],
    CAST(IOT_TEMP_VAL_C AS FLOAT) AS [Current_Temperature_C],
    CGO_COND_CD AS [Cargo_Condition_Code],
    RISK_CLS_TXT AS [Risk_Classification],
    DELAY_PROB_DEC AS [Delay_Probability],
    PRT_CNG_LVL AS [Port_Congestion_Level],
    RT_RSK_IDX AS [Route_Risk_Index]
FROM dbo.TBL_SC_FLEET_HIST_RAW;
GO

-- 3. Create a strict Read-Only contained database user for the AI Agent
-- (Azure SQL: CREATE LOGIN only works in master, so use a contained user instead)
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'USR_FDE_RO')
    CREATE USER USR_FDE_RO WITH PASSWORD = 'AgentPassword2026!';
GO

-- 4. Grant access ONLY to the semantic view, explicitly denying everything else
GRANT SELECT ON FDE_VIEWS.VW_ACTIVE_FLEET TO USR_FDE_RO;
DENY SELECT ON dbo.TBL_SC_FLEET_HIST_RAW TO USR_FDE_RO;
DENY INSERT, UPDATE, DELETE, ALTER ON SCHEMA::dbo TO USR_FDE_RO;
GO

-- # About line 33 :
-- ON SCHEMA::dbo: The dbo (Database Owner) schema is the default folder structure where your python ingestion script just dumped the TBL_SC_FLEET_HIST_RAW table. This target applies the rules to every single table or view currently inside dbo, or any tables you might add there in the future.