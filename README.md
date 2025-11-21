# 🧾 SMB FinSight

![CI](https://github.com/maxencebernardhub/smb-finsight/actions/workflows/ci.yml/badge.svg)
[![Latest Release](https://img.shields.io/github/v/release/maxencebernardhub/smb-finsight?color=blue)](https://github.com/maxencebernardhub/smb-finsight/releases)

**SMB FinSight** is a Python-based financial dashboard & analysis application designed for **small and medium-sized businesses**.  
It converts raw accounting entries into **standardized financial statements** and **KPIs**, using fully configurable, standard-specific mapping rules (PCG, ASPE, others to come).

The application supports:
- multi-standard accounting (FR PCG and CA ASPE in v0.2.0)
- normalized income statement generation (simplified → complete)
- optional secondary statements (e.g., French SIG)
- a unified financial-ratio engine (basic / advanced / full levels)
- flexible period selection (FY, YTD, MTD, last-month, custom)
- automatic CSV exports in a consistent hierarchical format

💡 Ideal for freelancers, entrepreneurs, CFOs, analysts, and accountants who want **clean, reproducible financial statements and KPIs** from simple CSV extracts — without relying on heavy accounting software.

---

## 📚 Table of Contents

- [Main Features](#️-main-features)
- [Supported Accounting Standards (v0.2.0)](#-supported-accounting-standards-v020)
- [Project Structure](#-project-structure-updated-for-v020)
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

- 📂 Reads accounting entries (`date`,`code`,`description`,`debit`,`credit`) from CSV file.  
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
- 🗂️ **Multi-standard architecture (NEW in v0.2.0)**  
  - Supports multiple accounting frameworks (FR PCG and CA ASPE; US GAAP / IFRS upcoming)  
  - Each standard provides:
    - its own mapping files  
    - its own ratio rules  
    - optional secondary statements (e.g., SIG for PCG)
- ⚙️ **Configurable display mode** (`table`, `csv`, `both`) via CLI or config file  
- 📄 **Generated CSV output is timestamped and stored automatically under `data/output/`**

---

## 📐 Supported Accounting Standards (v0.2.0)

SMB FinSight currently supports:

| Standard | Status | Details |
|---------|--------|---------|
| **FR PCG** | ✅ Fully supported | Income statement, SIG, canonical variables, full ratio set |
| **CA ASPE** | ✅ Fully supported | Income statement, ratios, CA ASPE–specific chart of accounts and sample entries |
| **US GAAP / IFRS** | 🚧 Planned | Will rely on secondary statements or a single mapping in a future release |

Each standard defines:
- its *own mapping files*
- its *own canonical variables*
- its *own ratio rules*
- optionally, its *own secondary statement*


---

## 📁 Project Structure (updated for v0.2.0)

```
smb-finsight/
├── smb_finsight_config.toml             # Global app configuration
├── pyproject.toml
├── config/
│   ├── standard_fr_pcg.toml             # Standard-specific mappings & rules (FR PCG)
│   ├── standard_ca_aspe.toml            # Standard-specific mappings & rules (CA ASPE)
│   └── standard_us_gaap.toml            # (future)
├── data/
│   ├── input/                           # User-provided accounting entries (examples)
│   │   ├── accounting_entries_fr_pcg.csv
│   │   └── accounting_entries_ca_aspe.csv
│   ├── output/                          # Generated CSV outputs
│   └── reference/
│       ├── fr_pcg.csv                   # List of valid PCG accounts
│       └── ca_aspe.csv                  # Generic CA ASPE chart of accounts template
├── mapping/
│   ├── income_statement_fr_pcg.csv      # Income statement mapping for FR PCG
│   ├── sig_fr_pcg.csv                   # SIG (soldes intermédiaires de gestion) mapping for FR PCG
│   └── income_statement_ca_aspe.csv     # Income statement mapping for CA ASPE
├── ratios/
│   ├── ratios_fr_pcg.toml               # All ratios/KPIs rules for FR PCG
│   └── ratios_ca_aspe.toml              # All ratios/KPIs rules for CA ASPE
├── src/
│   └── smb_finsight/
│       ├── __init__.py
│       ├── accounts.py
│       ├── cli.py
│       ├── config.py
│       ├── engine.py
│       ├── io.py
│       ├── mapping.py
│       ├── ratios.py                    # NEW core ratios engine
│       └── views.py
├── tests/
```


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

Example (FR PCG):

```toml
standard = "FR_PCG"

[fiscal_year]
start_date = "2025-01-01"
end_date = "2025-12-31"

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

### 1. `accounting_entries.csv` (required)

The input CSV must contain **both a date and a description** for each entry.

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
| `code`        | Yes      | text / integer   | Must match `fr_pcg.csv`               |
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

For FR PCG: file is fr_pcg.csv.
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
SMB FinSight uses `accounts_to_include` / `accounts_to_exclude` instead of legacy `code_range`.  


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

### Base command

```bash
python -m smb_finsight.cli \
  --scope statements|all_statements|ratios|all \
  --view simplified|regular|detailed|complete \
  --ratios-level basic|advanced|full \
  --display-mode table|csv|both \
  [--period fy|ytd|mtd|last-month|last-fy] \
  [--from-date YYYY-MM-DD] \
  [--to-date YYYY-MM-DD] \
  [--output OUTPUT_DIR]
```

If you do not specify `--output`, CSVs are written automatically to: 
`data/output/<timestamped-files>.csv` with timestamped filenames.
The accounting standard, mapping files and ratio rules are now loaded
automatically from the configuration files under `/config/`.

### 📦 CLI Quick Examples (v0.1.6+)

Here are ready-to-run commands demonstrating the most common use cases.

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


### ⏱️ Period selection (NEW in v0.1.5)

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

---

## 🟦 Secondary Statement: SIG (FR PCG)


SMB FinSight provides a full French-style SIG (Soldes Intermédiaires de Gestion)
based on the PCG.

- Mapping file: `/mapping/sig_fr_pcg.csv`  
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

This consistency is enforced by test `test_sig_consistency.py`.

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

The full test suite currently includes **13 tests** and all must pass before contributing.

Includes:

- IO validation  
- Template logic  
- SUM(; ; ) syntax  
- View filtering  
- Account-code validation 

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

### ✅ Completed (as of v0.2.0)
- [x] Full support for **FR PCG** (income statement + SIG + ratios)
- [x] Full support for **CA ASPE** (mapping, ratios, COA, sample entries)
- [x] Multi-standard architecture with standard-specific mapping & ratios
- [x] Complete ratio engine (basic / advanced / full levels)
- [x] Period engine (FY, YTD, MTD, last-month, custom)
- [x] Hierarchical statement rendering (simplified → complete)
- [x] CLI overhaul and consistent outputs
- [x] Normalized canonical measures across standards
- [x] Full test suite (13 tests)

### 🚧 In Progress
- [ ] US GAAP / IFRS mapping foundations

### 🧭 Planned
- [ ] Extend compatibility to **US GAAP / IFRS**.
- [ ] Add **database** feature (save **history** / **current** accounting entries)
- [ ] Improve Console UI/UX
- [ ] Add **projected** accounting entries.
- [ ] Add interactive visual dashboards.
- [ ] Web UI / lightweight desktop app
- [ ] Add Cash Flow
- [ ] Add AI
---

## 🕒 Version History

| Version | Date | Highlights | Tag |
|----------|------|-------------|------|
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
