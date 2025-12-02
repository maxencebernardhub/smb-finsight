# 🧾 SMB FinSight

![CI](https://github.com/maxencebernardhub/smb-finsight/actions/workflows/ci.yml/badge.svg)
[![Latest Release](https://img.shields.io/github/v/release/maxencebernardhub/smb-finsight?color=blue)](https://github.com/maxencebernardhub/smb-finsight/releases)

**SMB FinSight** is a Python-based financial dashboard & analysis application designed for **small and medium-sized businesses**.  
It converts raw accounting entries stored in the local database (fed via CSV imports) into **standardized financial statements** and **KPIs**, using fully configurable, standard-specific mapping rules (French PCG, Canadian ASPE, US GAAP and IFRS).

The application supports:
- multi-standard accounting (FR PCG, CA ASPE, US GAAP and IFRS)
- normalized income statement generation (simplified → complete)
- optional secondary statements (e.g., French SIG)
- a unified financial-ratio engine (basic / advanced / full levels)
- a unified multi-period computation engine (`compute_all_multi_period`)  
  generating statements, measures (canonical, extra and derived) and ratios  
  for any number of periods in a single pass (Python API)
- flexible period selection (FY, YTD, MTD, last-month, custom)
- automatic CSV exports in a consistent hierarchical format

Note: the CLI remains single-period only in version 0.4.0. Multi-period analysis is available through the Python API and will power the upcoming Web UI.

As of version **0.3.0**, SMB FinSight uses a local SQLite database as the single source of truth for all accounting entries. CSV files can still be imported using the `--import` CLI argument, but the dashboard always reads from the database.
Version **0.4.0+** added full CRUD operations, and version **0.4.5** extends the schema with the duplicate-resolution workflow.

As of version **0.4.5**, SMB FinSight introduces a complete duplicate-resolution
workflow. During CSV imports, entries that match an already-existing accounting
entry are **not inserted** into `entries` but instead stored in the new
`duplicate_entries` table with `resolution_status = "pending"`.
The CLI now provides commands to list, inspect and resolve these duplicates.

As of version **0.4.5**, SMB FinSight supports **four full accounting standards**:  
**French PCG**, **Canadian ASPE**, **US GAAP**, and **IFRS** — all mapped into a unif              ied canonical financial model allowing perfectly comparable KPIs and ratios across jurisdictions.


💡 Ideal for freelancers, entrepreneurs, CFOs, analysts, and accountants who want **clean, reproducible financial statements and KPIs** from simple CSV extracts — without relying on heavy accounting software.

---

## 📚 Table of Contents

- [Main Features](#️-main-features)
- [Supported Accounting Standards](#-supported-accounting-standards)
- [Project Structure](#-project-structure-updated-for-v040)
- [Installation](#-installation)
- [Configuration](#configuration)
- [Input Files](#input-files)
- [CLI Usage](#-cli-usage)
- [Financial Ratios & KPIs](#-financial-ratios--kpis)
- [Secondary Statement; SIG (FR PCG)](#-secondary-statement-sig-fr-pcg)
- [FinSight Sign Convention](#-finsight-sign-convention)
- [Output Format](#-output-format)
- [Quick Tests](#-quick-tests)
- [Contributing](#-contributing)
- [Roadmap](#-roadmap)
- [Version History](#-version-history)
- [License](#-license)

---

## ⚙️ Main Features

- 📂 Imports accounting entries from CSV files into the database using the `--import` CLI argument. 
- 🧮 Normalizes amounts (`amount = credit − debit`). 
- 📊 Aggregates entries according to **unified mapping files**.
- **Configuration** via `smb_finsight_config.toml`
- **Period selection**:
  - `--period fy` → full fiscal year
  - `--period ytd` → year-to-date
  - `--period mtd` → month-to-date
  - `--period last-month` → previous calendar month
  - `--period last-fy` → previous fiscal year
  - custom: `--from-date YYYY-MM-DD` / `--to-date YYYY-MM-DD`
- Automatic filtering of accounting entries based on selected period
- Display of applied period and number of entries kept
- 🧱 Supports **4 views**:  
  - **simplified** → levels ≤ 1  
  - **regular** → levels ≤ 2  
  - **detailed** → levels ≤ 3  
  - **complete** → full mapping + automatic listing of individual account codes 
- 💾 Exports hierarchical income statements with columns:  
  `display_order, id, level, name, type, amount` as a CSV file.
- 🔢 **Financial ratios & KPIs engine**  
  - 3 levels: `basic`, `advanced`, `full`  
  - Fully configurable via standard-specific TOML rule sets  
  - Canonical financial variables automatically computed from statements  
- 🗂️ **Multi-standard architecture and engine**  
  - Supports multiple accounting frameworks (FR PCG, CA ASPE, US GAAP and IFRS)  
  - Each standard provides:
    - its own mapping files  
    - its own ratio rules  
    - optional secondary statements (e.g., SIG for PCG)
- Full cross-standard compatibility: CLI commands, ratios, period selection and exports all work identically across every accounting standard
- ⚙️ **Configurable display mode** (`table`, `csv`, `both`) via CLI or config file  
- 📄 **Generated CSV output is timestamped and stored automatically under `data/output/`**
- 🗄️ Database-backed storage
  - All accounting entries are now stored in a local SQLite database
  - The financial dashboard always uses the database as the single source of truth
  - CSV files are no longer read directly during analysis.
  - CSV files can be imported at any time via the `--import` CLI argument
  - Duplicate detection is built-in, with suspected duplicates routed to a dedicated table
- 🔄 **Duplicate Resolution Workflow (v0.4.5)**
  - Duplicates detected during import are stored in `duplicate_entries`
  - New CLI commands to list, inspect, and resolve duplicates
  - Resolution metadata tracked (`resolution_status`, `resolution_at`,
    `resolved_by`, `resolution_comment`)
- 📈 **Unified multi-period computation engine (v0.3.5)**  
  - new `compute_all_multi_period()` function  
  - computes statements, measures (canonical, extra and derived) and ratios  
    for any number of periods in one pass  
  - optimized for dashboards, charts and financial comparisons
- 🗄️ **Complete CRUD interface (v0.4.0+)**
  - Add, update, soft-delete, restore accounting entries directly in the database
  - High-level CRUD operations exposed via the CLI `entries` command group
  - Fully orchestrated through `entries_service.py`
- 🔍 **Unknown Accounts Reporting (v0.4.0+)**
  - Detect unmapped or invalid account codes for any reporting period
  - Summaries by code + optional detailed listing
  - Based on chart-of-accounts prefix matching
- 🧹 **Improved CSV Import Validation (v0.4.0+)**
  - Rejects entries containing account codes not present in the chart of accounts
  - Ensures clean and consistent database content before analytical processing
- 🗂️ **Developer Tools**
  - `entries list` → entries for a fiscal/period range
  - `entries search` → full-DB unrestricted search
  - `entries delete` / `entries restore` → soft-delete cycle
  - `entries unknown-accounts` → validation & diagnostics
  - `entries duplicate` → access duplicate resolution workflow


The CLI continues to expose single-period commands only  
(FY, YTD, MTD, last-month, custom).


---

## 📐 Supported Accounting Standards

SMB FinSight natively supports **four accounting standards**, each mapped to a unified internal structure (“canonical measures”) so that ratios, aggregations and CLI behavior remain perfectly consistent across jurisdictions.

### 🇫🇷 French GAAP (PCG)
- Full P&L mapping  
- SIG (Soldes Intermédiaires de Gestion)  
- Dedicated chart of accounts (`fr_pcg.csv`)  
- Ratios pack adapted to French presentation

### 🇨🇦 Canadian ASPE
- Complete P&L mapping (nature of expense method)  
- Chart of accounts (`ca_aspe.csv`)  
- Full ratios compatibility  

### 🇺🇸 US GAAP
- Complete P&L mapping (nature of expense method)  
- US GAAP-friendly labels  
- Dedicated chart of accounts (`us_gaap.csv`)  
- Compatible with all KPI & ratio packs  

### 🌍 IFRS
- Complete IFRS P&L (nature of expense method)  
- IFRS-compliant labels (Operating profit, Profit before tax, Profit for the period)  
- Dedicated chart of accounts (`ifrs.csv`)  
- All ratios and derived measures fully supported  

Each standard defines:
- its *own mapping files*
- its *own canonical variables*
- its *own ratio rules*
- optionally, its *own secondary statement*

### Unified canonical model
Regardless of the standard, SMB FinSight produces:
- `revenue`  
- `cost_of_goods_sold`  
- `gross_margin`  
- `total_operating_expenses`  
- `operating_income`  
- `financial_result`  
- `income_tax_expense`  
- `net_income` (IFRS: “Profit for the period”)

This ensures **perfect comparability** between French PCG, ASPE, US GAAP and IFRS outputs.

---

## 📁 Project Structure (updated for v0.4.5)

```
smb-finsight/
├── smb_finsight_config.toml             # Global app configuration
├── pyproject.toml
├── config/
│   ├── standard_fr_pcg.toml             # Standard-specific mappings & rules (FR PCG)
│   ├── standard_ca_aspe.toml            # Standard-specific mappings & rules (CA ASPE)
│   ├── standard_us_gaap.toml            # Standard-specific mappings & rules (US GAAP)
│   └── standard_ifrs.toml               # Standard-specific mappings & rules (IFRS)
├── data/
│   ├── input/                           # Contains example CSV files that can be imported into the 
│   │                                    # database using the `--import` command.
│   │   ├── accounting_entries_fr_pcg.csv
│   │   ├── accounting_entries_ca_aspe.csv
│   │   ├── accounting_entries_us_gaap.csv
│   │   └── accounting_entries_ifrs.csv
│   ├── output/                          # Generated CSV outputs
│   └── reference/
│       ├── fr_pcg.csv                   # List of valid PCG accounts
│       ├── ca_aspe.csv                  # Generic CA ASPE chart of accounts template
│       ├── us_gaap.csv                  # Generic US GAAP chart of accounts template
│       └── ifrs.csv                     # Generic IFRS chart of accounts template
├── mapping/
│   ├── income_statement_fr_pcg.csv      # Income statement mapping for FR PCG
│   ├── sig_fr_pcg.csv                   # SIG (soldes intermédiaires de gestion) mapping for FR PCG
│   ├── income_statement_ca_aspe.csv     # Income statement mapping for CA ASPE
│   ├── income_statement_us_gaap.csv     # Income statement mapping for US GAAP
│   └── income_statement_ifrs.csv        # Income statement mapping for IFRS
├── ratios/
│   ├── ratios_fr_pcg.toml               # All ratios/KPIs rules for FR PCG
│   ├── ratios_ca_aspe.toml              # All ratios/KPIs rules for CA ASPE
│   ├── ratios_us_gaap.toml              # All ratios/KPIs rules for US GAAP
│   └── ratios_ifrs.toml                 # All ratios/KPIs rules for IFRS
├── src/
│   └── smb_finsight/
│       ├── __init__.py
│       ├── accounts.py
│       ├── cli.py
│       ├── config.py
│       ├── engine.py                    # Core single-period aggregation logic
│       ├── io.py
│       ├── mapping.py
│       ├── multi_periods.py             # Unified multi-period engine (v0.3.5)
│       ├── periods.py                   # Period parsing (FY/YTD/MTD/Custom)
│       ├── ratios.py                    
│       ├── views.py
│       ├── db.py                        # Database schema, CRUD, imports, and duplicate workflow (v0.4.0 / v0.4.5)
│       └── entries_service.py           # High-level CRUD, reporting, and duplicate resolution API (v0.4.0 / v0.4.5)
├── tests/
```

As of v0.4.0:
- `db.py` now exposes full CRUD operations (create/update/delete/restore)
- `entries_service.py` provides a business-level CRUD layer for the CLI & Web UI
- `accounts.py` includes improved account-code validation for CSV imports


---

## 🧩 Installation

```bash
git clone https://github.com/maxencebernardhub/smb-finsight.git
cd smb-finsight
python -m venv .venv
source .venv/bin/activate   # macOS / Linux
pip install -e .
```

---

### 🧩 Setup for Development

To install SMB FinSight with dev tools (Ruff & Pytest):

```bash
pip install -e ".[dev]"
```

---

## Configuration

### Configuration architecture summary

SMB FinSight loads configuration in this order:

1. **smb_finsight_config.toml** → global settings  
2. **config/standard_<standard>.toml** → standard-specific rules  
3. **mapping/** → mapping CSV files declared in the standard file  
4. **ratios/** → ratio rules declared in the standard file  

The CLI never loads mapping or ratios directly.


### 1. Global configuration (`smb_finsight_config.toml`)

This file defines:

- the selected accounting standard  
- fiscal year boundaries  
- display settings  
- optional balance-sheet and HR variables  

As of v0.3.0, SMB FinSight no longer reads accounting entries directly from CSV files.
All entries must be imported into the database using the CLI (--import), and the dashboard always reads from the database.

#### Example (FR PCG):

```toml
[accounting]
standard = "FR_PCG"
standard_config_file = "config/standard_fr_pcg.toml"

[fiscal_year]
start_date = "2025-01-01"
end_date = "2025-12-31"

[database]
engine = "sqlite"
path = "data/db/smb_finsight.sqlite"

[display]
mode = "table"
ratio_decimals = 2

[balance_sheet]
total_assets = 150000
total_equity = 45000
capital_employed = 80000
financial_debt = 25000

[hr]
average_fte = 52
```

#### Example: Using the IFRS standard

```toml
[accounting]
standard = "IFRS"
standard_config_file = "config/standard_ifrs.toml"
```

### 2. Standard-specific configuration (`config/standard_fr_pcg.toml`)

Each accounting standard provides:
- its own income-statement mapping
- optional secondary mapping (SIG for PCG)
- its own ratio rules

Example (excerpt):

```toml
[paths.mapping]
primary_mapping_file = "mapping/income_statement_fr_pcg.csv"
label_primary_statement = "Compte de résultat (FR PCG)"

secondary_mapping_file = "mapping/sig_fr_pcg.csv"
label_secondary_statement = "Soldes Intermédiaires de Gestion (SIG)"

[paths.ratios]
rules_file = "ratios/ratios_fr_pcg.toml"
```

This two-level configuration makes SMB FinSight fully multi-standard.

---
## Input Files

### 1. `accounting_entries.csv`


The input CSV is not read directly during analysis.
It is only used as an import source for the database via the `--import` argument.

The file must contain **a date, a code, and a description** for each entry.

Two input formats are supported:

#### 1) Debit/credit format

```csv
date,code,description,debit,credit
2025-01-02,622000,Office rent,1000.00,0.00
2025-01-05,706000,Consulting services,0.00,2500.00
```

#### 2) Signed amount format

```csv
date,code,description,amount
2025-01-10,623400,Software subscription,-49.99
```

- `description` (or `label`) → free text  
- `amount` is always internally computed as **credit – debit**
  - Expenses (6xxx accounts) normally result in negative amounts  
  - Revenues (7xxx accounts) normally result in positive amounts

➡️ *This format is now enforced starting from **v0.1.5***.

### ✔ Required columns summary (v0.1.5+)

| Column        | Required | Format           | Notes                              |
|---------------|----------|------------------|------------------------------------|
| `date`        | Yes      | YYYY-MM-DD       | Used for fiscal and period logic   |
| `code`        | Yes      | text / integer   | Must match the chart of accounts of the selected standard   |
| `description` | Yes      | text             | Free text, used for readability    |
| `debit`       | Optional | number           | Used if `amount` not provided      |
| `credit`      | Optional | number           | Used if `amount` not provided      |
| `amount`      | Optional | number           | Signed amount; overrides debit/credit |


⚠️ Starting from v0.1.6, all other inputs (mapping files, ratios rules,
account lists, standards) are loaded exclusively through TOML configuration
and no longer passed via CLI arguments.

---

### 2. `chart_of_accounts.csv` (required for each standard)

This file **must** list all valid account codes.

For FR PCG: file is `data/reference/fr_pcg.csv`.
Other standards provide their own chart of accounts.

```csv
account_number,name
701000,Ventes de produits finis
706000,Prestations de services
622001,Honoraires
…
```

Used to:

- Validate imported entries  
- Ignore unknown codes with a console message:  
  `Unknown account code XXXXX ignored`
- Attach accounts automatically in **complete** view

---

### 3. Mapping templates

Mapping templates define how each account (6xxx / 7xxx) contributes to the
different lines of the statement.

Two CSV templates exist:

#### 1) Detailed income statement

```csv
display_order,id,name,type,level,accounts_to_include,accounts_to_exclude,formula,canonical_measure,notes
10,1,Ventes de marchandises,acc,3,707000;709700,,,
20,11,Chiffre d'affaires net,calc,2,,,=1+2,revenue,
...
```
SMB FinSight uses `accounts_to_include` / `accounts_to_exclude` instead of legacy `code_range`. The system performs strict prefix matching: “701*” matches all accounts starting with “701”.
 


- `level 0` = top categories  
- `level 1` = regular view  
- `level 2` = detailed  
- `level 3` = parent of account-level rows  
- `level 4` (added automatically in view=complete)

Example:
level 0  → REVENUE
  level 1    → Sales
    level 2      → Sales of finished products
      level 3        → 701*;702*
        level 4          → individual accounts (auto-generated in “complete” view)


#### 2) Secondary Statement: `SIG` (FR PCG)

Same structure as above, but specific French SIG definitions

➡️ SMB FinSight aggregates amounts by selecting rows based on 
`accounts_to_include` / `accounts_to_exclude`.


---

## 🧮 CLI Usage

Note: the CLI operates on a single reporting period per command.  
Multi-period analytics are available through the Python API  
via `compute_all_multi_period()` and will be exposed in the Web UI.
There is currently no CLI command for exporting multiple periods at once.


### Base command

```bash
python -m smb_finsight.cli \
  --import CSV_PATH \
  --scope statements|all_statements|ratios|all \
  --view simplified|regular|detailed|complete \
  --ratios-level basic|advanced|full \
  --display-mode table|csv|both \
  [--period fy|ytd|mtd|last-month|last-fy] \
  [--from-date YYYY-MM-DD] \
  [--to-date YYYY-MM-DD] \
  [--output OUTPUT_DIR]
```

`--import` : Import accounting entries from the given CSV file into the database.
`--import` must be provided before any dashboard filtering arguments.

When `--import` is used, entries are added to the database first, and the dashboard is computed immediately afterwards, unless the user explicitly suppresses output via display settings.

If you do not specify `--output`, CSVs are written automatically to: 
`data/output/<timestamped-files>.csv` with timestamped filenames.
The accounting standard, mapping files and ratio rules are now loaded
automatically from the configuration files under `/config/`.

### 📁 Database CRUD Commands (v0.4.0+)

SMB FinSight now includes a full CRUD interface for accounting entries stored
in the SQLite database. These commands are grouped under:

    python -m smb_finsight.cli entries <subcommand>

Available subcommands:

#### 1) List entries for a period
```bash
python -m smb_finsight.cli entries list --period ytd
python -m smb_finsight.cli entries list --from-date 2025-01-01 --to-date 2025-03-31
```

#### 2) Search the entire database
```bash
python -m smb_finsight.cli entries search --code-prefix 70
python -m smb_finsight.cli entries search --description-contains stripe
```

#### 3) Soft-delete an entry
```bash
python -m smb_finsight.cli entries delete 42 --reason "duplicate"
```

#### 4) Restore a previously deleted entry
```bash
python -m smb_finsight.cli entries restore 42
```

#### 5) Unknown accounts reporting
```bash
python -m smb_finsight.cli entries unknown-accounts --period fy
python -m smb_finsight.cli entries unknown-accounts --show-entries
```

These database-focused commands allow developers, power users, and the future
Web UI (v0.5.x) to inspect data, clean it, and validate it independently of
the analytical dashboard.

### 🔄 Duplicate Resolution Workflow (v0.4.5)

During CSV imports, SMB FinSight automatically detects exact duplicate entries.
Instead of inserting them into the main entries table, they are stored in
duplicate_entries with resolution_status="pending".

You can inspect and resolve these duplicates through the CLI:

#### 1) View duplicate statistics

```bash
python -m smb_finsight.cli entries duplicates stats
```
Shows counts:
- pending
- kept
- discarded

#### 2) List duplicates

```bash
python -m smb_finsight.cli entries duplicates list
python -m smb_finsight.cli entries duplicates list --status all
```
Shows Candidate vs Existing entry with minimal columns.

#### 3) Show details for a specific duplicate

```bash
python -m smb_finsight.cli entries duplicates show <ID>
```

Side-by-side view of:
- duplicate candidate
- existing matched entry

#### 4) Resolve a duplicate

Keep the candidate (= insert it into entries):
```bash
python -m smb_finsight.cli entries duplicates resolve <ID> --keep --comment "not a duplicate"
```

Discard it:
```bash
python -m smb_finsight.cli entries duplicates resolve <ID> --discard --comment "true duplicate"
```

Resolution updates:
- resolution_status → kept | discarded
- resolution_at → timestamp
- resolved_by → cli
- resolution_comment → optional


### 📦 CLI Quick Examples (v0.3.0+)

Here are ready-to-run commands demonstrating the most common use cases.

NB: If the database is empty, SMB FinSight will warn you and show no entries.

#### 1) Income statement (regular view)

```bash
python -m smb_finsight.cli \
    --scope statements \
    --view regular \
    --display-mode table
```

#### 2) All statements (income statement + SIG)

```bash
python -m smb_finsight.cli \
    --scope all_statements \
    --view detailed \
    --display-mode both
```

#### 3) Ratios (full level)

```bash
python -m smb_finsight.cli \
    --scope ratios \
    --ratios-level full \
    --display-mode table
```

#### 4) First-time import

```bash
python -m smb_finsight.cli --import data/input/accounting_entries_2024.csv
```

Then run dashboard (uses the database):
```bash
python -m smb_finsight.cli --period ytd
```

### ⏱️ Period selection

SMB FinSight can generate income statements for a specific time period.

#### Predefined periods

```bash
--period fy          # full fiscal year (from config)
--period ytd         # year to date
--period mtd         # month to date
--period last-month  # previous calendar month
--period last-fy     # previous fiscal year
```


#### Custom periods

```bash
--from-date 2025-03-01
--to-date 2025-06-30
```

#### Priority rules:

1) If `--period` is provided → it overrides `from-date` / `to-date`  
2) Else custom from/to dates apply  
3) Else → default to fiscal year  

When running, the CLI prints:

```bash
Applied period: Month to date (2025-11-01 → 2025-11-23)
Entries kept after period filter: 42
```

### CLI output example after period filtering

When running with date-based filters, the CLI prints:

```bash
Applied period: Last month (2025-10-01 → 2025-10-31)
Entries kept after period filter: 18
```

---

## 📊 Financial Ratios & KPIs

SMB FinSight now computes a full set of ratios and KPIs from both:

- the income statement  
- the secondary statement (e.g., SIG for PCG)  
- optional balance-sheet variables from `smb_finsight_config.toml`  

### Canonical Financial Measures (computed before ratios)

Examples (FR PCG):

- revenue  
- gross_margin  
- operating_income  
- net_income  
- external_charges  
- personnel_expenses  
- financial_debt  
- cash_and_equivalents  
- total_assets  
- total_equity  
- average_fte  
...

Before computing ratios, SMB FinSight merges all canonical measures coming 
from the income statement, the secondary statement (e.g. SIG), and optional 
balance-sheet variables. This guarantees complete coverage for all ratio levels.

ℹ️ If certain ratios appear as `NaN`, it means one of their required canonical measures
was not provided in `smb_finsight_config.toml` (e.g., total_assets, total_equity, 
average_fte…).

### Ratio levels:
- **basic** → margins, value added, operating income  
- **advanced** → ROA, ROE, ROCE, CAF, external charges %, personnel expenses %  
- **full** → liquidity & rotation KPIs (DSO, DPO, DIO), gearing, interest coverage, equity ratio  

### Ratio rule engine
Rules are defined in the following file: `ratios/ratios_<standard>.toml`

Example (PCG):

```toml
[basic.gross_margin_pct]
formula = "(gross_margin / revenue) * 100"
unit = "percent"
label = "Marge brute (%)"
```

As of v0.3.5, all ratios and underlying measures may also be computed  
for multiple periods using the unified `compute_all_multi_period()` function.
The CLI remains single-period.


---

## 🟦 Secondary Statement: SIG (FR PCG)


SMB FinSight provides a full French-style SIG (Soldes Intermédiaires de Gestion)
based on the PCG.

- Mapping file: `mapping/sig_fr_pcg.csv`  
- Sign convention (FinSight):
  - products (7*) are **positive**  
  - charges (6*) are **negative**  
  → all SIG subtotals are computed using **simple algebraic sums**.

Key subtotals available:
- Marge commerciale  
- Marge de production  
- Valeur ajoutée  
- Excédent Brut d’Exploitation (EBE)  
- Résultat d’exploitation  
- Résultat financier  
- Résultat courant avant impôts  
- Résultat exceptionnel  
- Résultat de l’exercice (net)

Key SIG subtotals such as Marge commerciale, Valeur ajoutée or EBE
also populate canonical variables used by the ratio engine.

The SIG result is identical to:
- the result from the detailed view, and  
- the raw sum of all 6* and 7* accounting entries
(assuming no exceptional entries outside classes 6 and 7).

➡️ SIG is specific to French PCG.  
Other accounting standards may define a different secondary statement or none at all.

SIG is loaded automatically if secondary_mapping_file is defined in the standard’s TOML configuration.

---

## 🔢 FinSight Sign Convention

| Element | Debit | Credit | Result |
|--------|--------|---------|--------|
| Expenses (6*) | + | – | negative |
| Revenues (7*) | – | + | positive |

Formula rule:  
`Result = Revenues + Expenses`

This sign convention is applied consistently across all:
- mappings
- derived canonical measures
- financial ratios
- SIG subtotals

---

## 📤 Output Format

All generated CSVs follow the **same column order**:

```csv
display_order,id,level,name,type,amount
```

Generated CSV filenames follow this pattern:

- income_statement_YYYY-MM-DD-HHMMSS.csv
- secondary_statement_YYYY-MM-DD-HHMMSS.csv
- ratios_YYYY-MM-DD-HHMMSS.csv

Files are saved under `data/output/` unless `--output` overrides this.

When using --display-mode both, the table is printed to the console and a CSV is exported simultaneously.

Example (`--display-mode both`):

- Display table in the console
- Export CSV to data/output/


---

## 🧪 Quick Tests

Run all automated tests and static checks:
```bash
pytest -q
ruff check src tests
ruff format --check src tests
```

The full test suite currently includes **32 tests** (including multi-period orchestration).

Includes:

- IO validation  
- Template logic  
- SUM(; ; ) syntax  
- View filtering  
- Account-code validation 
- CA ASPE  
- US GAAP  
- IFRS
- Multi-period orchestration

### SIG consistency tests

Two tests ensure the correctness of the SIG mapping:

- `test_sig_consistency.py`
  Ensures:  
  **result(detailed) == result(sig) == raw sum of all 6* and 7* entries** 
  This guarantees perfect alignment between the SIG, the detailed income
  statement, and the underlying accounting entries.

- `test_sig_internal.py`  
  Verifies internal correctness of key SIG subtotals  
  (Marge commerciale, Marge de production, Valeur ajoutée) using
  a synthetic dataset.

### Ratio tests

The ratio engine is validated by `tests/test_ratios.py`, covering:
- derived measures
- safe expression evaluation
- basic/advanced/full cumulative levels

Quick command to test ratios:

```bash
python -m smb_finsight.cli --scope ratios --ratios-level full --display-mode table
```

---

## 🤝 Contributing

Set up a local development environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests && ruff format --check src tests
pytest -q
```

Please ensure all tests pass and code is linted before pushing.
Pull requests are welcome!

---

## 🚀 Roadmap

### ✅ Completed (as of v0.4.5)
- [x] Full support for **FR PCG** (income statement + SIG + ratios)
- [x] Full support for **CA ASPE** (mapping, ratios, COA, sample entries)
- [x] Multi-standard architecture with standard-specific mapping & ratios
- [x] Complete ratio engine (basic / advanced / full levels)
- [x] Period engine (FY, YTD, MTD, last-month, custom)
- [x] Hierarchical statement rendering (simplified → complete)
- [x] CLI overhaul and consistent outputs
- [x] Normalized canonical measures across standards
- [x] Full test suite (32 tests)
- [x] Database module (store accounting entries)
- [x] Unified multi-period engine (statements + measures + ratios) — v0.3.5
- [x] Full CRUD database layer — v0.4.0
- [x] Duplicate resolution workflow (v0.4.5): database schema upgrade, CLI commands, service layer


### 🚧 In Progress
- [ ] Add interactive visual dashboards / WebUI

### 🧭 Planned
- [ ] Add webview wrapper
- [ ] Add **forecast** and **objectives** modules.
- [ ] Add **Cash Flow** module
- [ ] Add AI-assisted insights
---

## 🕒 Version History

| Version | Date | Highlights | Tag |
|----------|------|-------------|------|
| **0.4.5** | Dec 2025 | Duplicate resolution workflow (DB schema migration, entries duplicates CLI commands, service-layer API) | [v0.4.5](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.4.5) |
| **0.4.0** | Nov 2025 | Full CRUD database layer, entries_service, CLI entries subcommands, unknown accounts reporting | [v0.4.0](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.4.0) |
| **0.3.5** | Nov 2025 | Unified multi-period engine (`compute_all_multi_period`), metadata improvements, extended test suite | [v0.3.5](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.3.5) |
| **0.3.0** | Nov 2025 | New database-backed architecture, SQLite database, new `--import` CLI command, duplicate detection engine, configuration refactor | [v0.3.0](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.3.0) |
| **0.2.5** | Nov 2025 | Added US GAAP + IFRS support, updated mappings, COA, ratios, full test suites | [v0.2.5](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.2.5) |
| **0.2.0** | Nov 2025 | Added full CA ASPE support (mapping, ratios, CA ASPE COA, sample entries) | [v0.2.0](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.2.0) |
| **0.1.6** | Nov 2025 | Ratios engine, multi-standard support, PCG canonical variables, new CLI, config overhaul | [v0.1.6](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.6) |
| **0.1.5** | Nov 2025 | Fiscal-year config, period selection (FY/YTD/MTD/last-month/custom), date+description enforced | [v0.1.5](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.5) |
| **0.1.4** | Nov 2025 | Full SIG (PCG) view, improved reliability of detailed mapping | [v0.1.4](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.4) 
| **0.1.3** | Nov 2025 | Unified mapping, new CLI, complete income statement view | [v0.1.3](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.3) |
| **0.1.2** | Nov 2025 | Internal documentation update | [v0.1.2](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.2) |
| **0.1.1** | Nov 2025 | Updated README (CI badge, contributing), CI improvements | [v0.1.1](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.1) |
| **0.1.0** | Nov 2025 | Initial release: core engine, mappings, CLI, tests | [v0.1.0](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.0) |

---

## 📜 License

MIT License © Maxence Bernard  
See [`LICENSE`](LICENSE) for details.
