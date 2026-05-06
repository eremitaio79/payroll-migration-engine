# payroll-migration-engine

Python ETL and migration CLI for payroll data, built to extract records from Oracle, normalize them into a relational PostgreSQL model, validate data quality before load, and refresh downstream JSON cache layers in a controlled way.

This repository is a sanitized public case study derived from a real migration workflow. Sensitive credentials, institution-specific object names, generated reports, and internal operational traces were removed before publication.

## Problem context

The original migration scenario involved a payroll domain with high data volume, multiple dependent entities, and a source environment that was useful for consultation but not suitable as a long-term operational foundation for the target system.

The core pain points were practical:

- a very large mass of payroll data arrived through a single wide Oracle view, which is convenient for legacy consultation but poor as a durable application data model
- source data arrived denormalized and operationally noisy
- payroll records needed to be preserved with relational consistency across employees, links, payroll references, items, and snapshots
- the destination platform needed safer and more queryable data than the legacy extraction format could provide
- the migration could not rely on blind bulk loads because validation gaps would become downstream product defects
- the team needed repeatable execution, not a one-off script that only worked on the machine of whoever wrote it

## Why the application was developed

This application was developed to turn a fragile migration challenge into a controlled operational workflow.

Instead of treating the job as "extract and dump," the tool was structured to support the full path from source interrogation to normalized persistence:

- break a single dense payroll source into a normalized relational model designed for downstream application use
- inspect Oracle data before load
- detect mapping inconsistencies early
- transform payroll records into a target model with explicit entity boundaries
- load PostgreSQL with idempotent, auditable steps
- generate cache artifacts required by downstream consumers
- support both assisted human operation and repeatable scripted execution

In short, the tool exists because the real problem was not only moving data. The real problem was moving it with confidence.

## Why this project matters

This was not a toy script. The application was designed to support a high-detail migration flow with:

- Oracle extraction by year, month, or bounded date range
- normalization into a multi-table PostgreSQL schema
- deduplicated and idempotent loading
- pre-load diagnostics and Markdown validation reports
- JSON cache generation and scoped cache refresh workflows
- an interactive CLI for guided execution plus a flag-driven mode for automation

It was also one of the real-world validations of my private internal SDD blueprint for structured software delivery.

## Core workflows

### 1. Migration

Reads Oracle source views, transforms payroll records into normalized entities, and loads PostgreSQL tables with execution tracking and error capture.

### 2. Validation-only mode

Runs extraction and transformation without writing to PostgreSQL, producing diagnostics that help detect mapping gaps, payroll inconsistencies, and relationship issues before a real load.

### 3. Dry-run mode

Exercises the extraction and transformation path without persisting data, useful for operational rehearsal and troubleshooting.

### 4. Cache generation

Builds JSON payloads from the normalized PostgreSQL model for downstream consumption.

### 5. Scoped cache refresh

Supports refresh by payroll competence, by competence plus employee registration, or by full year when an explicit confirmation flag is provided.

### 6. Schema generation

Generates and optionally applies the PostgreSQL schema expected by the ETL flow, with connection validation and explicit confirmation.

## Architecture highlights

- `main.py`: CLI entrypoint, orchestration, interactive menu, and operational flows
- `extract/`: Oracle queries for payroll reference data and payroll records
- `transform/`: normalization logic for payroll entities, items, links, and snapshots
- `load/`: PostgreSQL loaders, upsert-style preparation, and load auditing
- `validation/`: diagnostics and Markdown report generation
- `cache/`: JSON payload assembly and cache refresh logic
- `db/`: Oracle/PostgreSQL connectivity and schema generation helpers
- `utils/`: logging, validation helpers, normalization helpers, and utility routines

## Tech stack

- Python
- SQLAlchemy
- pandas
- Typer
- Rich
- Oracle Database driver
- PostgreSQL / psycopg2

## Running locally

### 1. Create a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in Oracle and PostgreSQL credentials.

If your Oracle environment requires thick mode, set `ORACLE_CLIENT_LIB_DIR` to the Oracle Instant Client directory.

### 4. Start the interactive menu

```powershell
python main.py
```

### 5. Or run directly with flags

```powershell
python main.py --ano 2026 --validate-only --verbose
python main.py --ano 2026 --mes 1 --dry-run --verbose
python main.py --ano 2026 --mes 1 --generate-cache --refresh-cache-competencia --verbose
```

## Example commands

```powershell
python main.py --ano 2026 --mes 1 --data-inicio 2026-01-01 --data-fim 2026-01-02 --verbose
python main.py --ano 2026 --mes 1 --data-inicio 2026-01-01 --data-fim 2026-01-05 --validate-only --verbose --report-md
python main.py --ano 2026 --generate-cache --refresh-cache-ano --force-year-refresh --verbose
```

## Schema artifacts

The repository includes static SQL artifacts for the normalized PostgreSQL model:

- `schema_postgres.sql`
- `schema_postgres_transactional.sql`

The interactive CLI can also generate and apply a schema script at runtime to a target PostgreSQL database after validating the connection.

## Notes on publication

- This public version uses generic source object names such as `PAYROLL_FOLHAS_VIEW` and `PAYROLL_CHECKS_VIEW`.
- Generated reports and local environment files are intentionally excluded from version control.
- The original internal project remains private and unchanged.
