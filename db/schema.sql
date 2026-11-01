-- Legacy claims platform schema, circa a fictional 2011 go-live, never cleaned up since.
-- Applied automatically on first container init via docker-entrypoint-initdb.d.
--
-- Deliberate "legacy" quirks (documented in record/1-truth/DICT-legacy-schema.md):
--   1. Cryptic abbreviated column names (CLM_STS_CD, ADJ_RSN_2, MBR_ID_NBR, ...)
--   2. Dates stored as CHAR(8) 'YYYYMMDD' strings, not DATE
--   3. Status/reason/type codes are bare strings resolved via STS_CD_LKUP, not enums
--   4. Inconsistent money typing: CLM_AMT is NUMERIC, ADJ_AMT is a VARCHAR like '$123.45'
--   5. Sometimes-null columns: ADJ_RSN_2, PRV_TIN, MBR_TERM_DT

CREATE TABLE STS_CD_LKUP (
    CD_TYP      VARCHAR(10) NOT NULL,   -- e.g. 'CLM_STS', 'DISP_STS', 'DISP_TYP', 'ADJ_RSN', 'NET_STS'
    CD_VAL      VARCHAR(10) NOT NULL,   -- e.g. 'DUP', 'PD', 'DEN'
    CD_DESC     VARCHAR(100) NOT NULL,
    PRIMARY KEY (CD_TYP, CD_VAL)
);

CREATE TABLE PLAN_MAST (
    PLAN_CD     VARCHAR(10) PRIMARY KEY,
    PLAN_NM     VARCHAR(100) NOT NULL,
    PLAN_YR     SMALLINT NOT NULL
);

CREATE TABLE MBR_MAST (
    MBR_ID_NBR  INTEGER PRIMARY KEY,
    MBR_LST_NM  VARCHAR(50) NOT NULL,
    MBR_FST_NM  VARCHAR(50) NOT NULL,
    MBR_DOB     CHAR(8) NOT NULL,       -- YYYYMMDD
    PLAN_CD     VARCHAR(10) NOT NULL REFERENCES PLAN_MAST(PLAN_CD),
    MBR_STS_CD  VARCHAR(10) NOT NULL,   -- resolve via STS_CD_LKUP(CD_TYP='MBR_STS')
    MBR_EFF_DT  CHAR(8) NOT NULL,       -- YYYYMMDD
    MBR_TERM_DT CHAR(8)                 -- YYYYMMDD, NULL while the member is still active
);

CREATE TABLE PRV_MAST (
    PRV_ID_NBR    INTEGER PRIMARY KEY,
    PRV_NM        VARCHAR(100) NOT NULL,
    PRV_TIN       VARCHAR(9),           -- NULL for providers onboarded before TIN capture began
    PRV_NET_STS_CD VARCHAR(10) NOT NULL, -- resolve via STS_CD_LKUP(CD_TYP='NET_STS')
    PRV_SPEC_CD   VARCHAR(10) NOT NULL
);

CREATE TABLE CLM_HDR (
    CLM_ID_NBR    INTEGER PRIMARY KEY,
    MBR_ID_NBR    INTEGER NOT NULL REFERENCES MBR_MAST(MBR_ID_NBR),
    PRV_ID_NBR    INTEGER NOT NULL REFERENCES PRV_MAST(PRV_ID_NBR),
    DT_OF_SVC     CHAR(8) NOT NULL,     -- YYYYMMDD
    CLM_SUBMIT_DT CHAR(8) NOT NULL,     -- YYYYMMDD
    PROC_CD       VARCHAR(10) NOT NULL,
    CLM_STS_CD    VARCHAR(10) NOT NULL, -- resolve via STS_CD_LKUP(CD_TYP='CLM_STS')
    CLM_AMT       NUMERIC(10,2) NOT NULL,
    ADJ_AMT       VARCHAR(20),          -- e.g. '$123.45'; NULL until adjudicated
    ADJ_RSN_CD    VARCHAR(10),          -- primary reason, resolve via STS_CD_LKUP(CD_TYP='ADJ_RSN')
    ADJ_RSN_2     VARCHAR(10),          -- secondary reason; populated only when a second factor applies
    VISIT_ID      VARCHAR(20),          -- groups claims from the same visit; not always set
    NOTE_TXT      VARCHAR(255)          -- free text, meaning depends on CLM_STS_CD
);

CREATE TABLE DISP_HDR (
    DISP_ID_NBR    INTEGER PRIMARY KEY,
    CLM_ID_NBR     INTEGER NOT NULL REFERENCES CLM_HDR(CLM_ID_NBR),
    DISP_TYP_CD    VARCHAR(10) NOT NULL, -- resolve via STS_CD_LKUP(CD_TYP='DISP_TYP'): DUP, BIL, DOC, COV
    DISP_FILED_DT  CHAR(8) NOT NULL,     -- YYYYMMDD
    DISP_STS_CD    VARCHAR(10) NOT NULL, -- resolve via STS_CD_LKUP(CD_TYP='DISP_STS')
    DISP_RESLN_AMT NUMERIC(10,2),        -- NULL until resolved
    DISP_RESLN_DT  CHAR(8)               -- YYYYMMDD, NULL until resolved
);

INSERT INTO STS_CD_LKUP (CD_TYP, CD_VAL, CD_DESC) VALUES
    ('CLM_STS', 'PD',  'Paid'),
    ('CLM_STS', 'DEN', 'Denied'),
    ('CLM_STS', 'PND', 'Pending'),
    ('MBR_STS', 'ACT', 'Active'),
    ('MBR_STS', 'TRM', 'Terminated'),
    ('NET_STS', 'INN', 'In network'),
    ('NET_STS', 'OON', 'Out of network'),
    ('ADJ_RSN', 'DUP', 'Duplicate claim'),
    ('ADJ_RSN', 'BIL', 'Billing error'),
    ('ADJ_RSN', 'DOC', 'Missing documents'),
    ('ADJ_RSN', 'COV', 'Not covered'),
    ('DISP_TYP', 'DUP', 'Duplicate denial'),
    ('DISP_TYP', 'BIL', 'Billing error'),
    ('DISP_TYP', 'DOC', 'Missing documents'),
    ('DISP_TYP', 'COV', 'Coverage denial'),
    ('DISP_STS', 'OPN', 'Open'),
    ('DISP_STS', 'RSLV', 'Resolved'),
    ('DISP_STS', 'ESC', 'Escalated to adjuster');
