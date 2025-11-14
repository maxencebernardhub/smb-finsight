# 🧾 SMB FinSight

![CI](https://github.com/maxencebernardhub/smb-finsight/actions/workflows/ci.yml/badge.svg)
[![Latest Release](https://img.shields.io/github/v/release/maxencebernardhub/smb-finsight?color=blue)](https://github.com/maxencebernardhub/smb-finsight/releases)

**SMB FinSight** is a Python-based financial dashboard & analysis application designed for **small and medium-sized businesses**.  
It aggregates **accounting entries (accounts 6 & 7)** from a CSV file to automatically produce **normalized income statements** (simplified or regular) based on the French *Plan Comptable Général* (PCG).

💡 Ideal for freelancers, entrepreneurs, CFOs, CEOs of SMBs, accountants or analysts who want to automate financial KPIs and income statement generation using simple CSV exports.

---

## 📚 Table of Contents

- [Main Features](#-main-features)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Configuration](#configuration)
- [Input Files](#input-files)
- [CLI Usage](#-cli-usage)
- [Sig View](#sig-view-pcg)
- [FinSight Sign Convention](#-finsight-sign-convention)
- [Output Format](#-output-format)
- [Quick Tests](#-quick-tests)
- [Contributing](#-contributing)
- [Roadmap](#-roadmap)
- [Version History](#-version-history)
- [License](#-license)

---

## ⚙️ Main Features

- 📂 Reads accounting entries (`code`, `debit`, `credit`) from CSV file.  
- 🧮 Normalizes amounts (`amount = credit − debit`). 
- 📊 Aggregates entries according to a **single unified mapping file**:  
  `detailed_income_statement_pcg.csv`.
- **Fiscal year configuration** via `smb_finsight_config.toml`
- **Period selection (NEW in v0.1.5)**:
  - `--period fy` → full fiscal year
  - `--period ytd` → year-to-date
  - `--period mtd` → month-to-date
  - `--period last-month` → previous calendar month
  - `--period last-fy` → previous fiscal year
  - custom: `--from-date YYYY-MM-DD` / `--to-date YYYY-MM-DD`
- Automatic filtering of accounting entries based on selected period
- Display of applied period and number of entries kept
- 🧱 Supports **5 views**:  
  - **simplified** → levels ≤ 1  
  - **regular** → levels ≤ 2  
  - **detailed** → levels ≤ 3  
  - **complete** → full mapping + automatic listing of individual account codes from the PCG 
  - **sig** → [French SIG (Soldes Intermédiaires de Gestion)](#sig-view-pcg) based on PCG
- 🧾 SIG view uses a dedicated PCG mapping (`sig_pcg.csv`) fully compliant with FinSight's algebraic sign convention.
- 🧰 Validates imported account codes using a user-provided **list_of_accounts** file (`pcg.csv`).
- 💾 Exports hierarchical income statements with columns:  
  `display_order, id, level, name, type, amount` as a CSV file.

---

## 📁 Project Structure (updated for v0.1.5)

```
smb-finsight/
├── smb_finsight_config.toml # Fiscal year configuration (NEW). Example:
│       [fiscal_year]
│       start_date = "2025-01-01"
│       end_date = "2025-12-31"
├── src/
│   └── smb_finsight/
│       ├── __init__.py
│       ├── cli.py # CLI with new --period / --from-date / --to-date flags
│       ├── io.py # Accounting entry loader (date + description required)
│       ├── periods.py # Period engine: fy, ytd, mtd, last-month, custom (NEW)
│       ├── config.py # Loads fiscal year config (NEW in 0.1.5)
│       ├── mapping.py # Mapping templates handler
│       ├── engine.py # Core aggregation engine
│       ├── views.py # All output views (simplified → complete)
│       └── accounts.py # PCG accounts loader + validator
├── data/
│   ├── mappings/
│   │   ├── detailed_income_statement_pcg.csv
│   │   ├── sig_pcg.csv
│   │   └── legacy/
│   │       ├── simplified_income_statement_pcg.csv
│   │       └── regular_income_statement_pcg.csv
│   └── accounts/
│       └── pcg.csv # List of accounts
├── examples/
│   ├── accounting_entries_large_with_description.csv # Updated to include date + description
│   ├── accounting_entries_small.csv
│   ├── accounting_entries_large.csv
│   ├── out_xxx.csv* # tous les fichiers de sortie
├── tests/
│   ├── test_periods.py # NEW
│   ├── test_engine_core.py
│   ├── test_mapping_template.py
│   ├── test_views_and_ordering.py
│   ├── test_sig_consistency.py
│   ├── test_sig_internal.py
└── pyproject.toml
```

Note: example CSV files in /examples/ are continuously updated to match the required input format (date + description). They are used in tests and CLI examples.

🗂️ Legacy mappings files remain available in data/mappings/legacy/ for anyone who wants to generate simplified or regular PCG statements without the unified mapping.

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

**NEW in v0.1.5**

SMB FinSight uses a TOML configuration file to define the current fiscal year.

### File: `smb_finsight_config.toml`

```toml
[fiscal_year]
start_date = "2025-01-01"
end_date = "2025-12-31"
```

This fiscal year is used when:
- no period is specified (`--period fy`)
- a custom period omits `--from-date` or `--to-date`
- computing YTD or MTD (clamped inside FY)
- generating “last-month” or “last-fy”

Without this file, the CLI cannot run any FY/YTD/MTD/last-month/last-fy period selection.
If the config file is missing or invalid, the CLI will raise a clear error.


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
| `code`        | Yes      | text / integer   | Must match `pcg.csv`               |
| `description` | Yes      | text             | Free text, used for readability    |
| `debit`       | Optional | number           | Used if `amount` not provided      |
| `credit`      | Optional | number           | Used if `amount` not provided      |
| `amount`      | Optional | number           | Signed amount; overrides debit/credit |


---

### 2. `pcg.csv` (required)

This file **must** list all valid account codes (PCG or custom user chart of accounts):

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

### 3. Mapping templates (PCG)

Mapping templates define how each account (6xxx / 7xxx) contributes to the
different lines of the income statement.

Two CSV templates exist:

#### 1) Detailed income statement

```csv
id,level,name,code_range
100,0,REVENUE,
110,1,Sales of goods,70*
111,2,Sales of finished products,701*;702*
...
```
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


#### 2) SIG (Soldes Intermédiaires de Gestion)

Same structure as above, but specific French SIG definitions

➡️ **SMB FinSight aggregates amounts by selecting rows matching each `code_range`.**


---

## 🧮 CLI Usage

### Base command

```bash
python -m smb_finsight.cli \
    --accounting-entries <path/to/entries.csv> \
    --list-of-accounts <path/to/accounts.csv> \
    --template <path/to/mapping.csv> \
    --view <simplified|regular|detailed|complete|sig> \
    --output <output.csv> \
    [--period fy|ytd|mtd|last-month|last-fy] \
    [--from-date YYYY-MM-DD] \
    [--to-date YYYY-MM-DD]
```

### 📦 CLI Quick Examples (v0.1.5+)

Here are ready-to-run commands demonstrating the most common use cases.

#### 1) Full fiscal year (FY)

```bash
python -m smb_finsight.cli \
    --accounting-entries examples/accounting_entries_large.csv \
    --list-of-accounts data/accounts/pcg.csv \
    --template data/mappings/detailed_income_statement_pcg.csv \
    --view regular \
    --period fy \
    --output out_fy.csv
```

#### 2) Last month only

```bash
python -m smb_finsight.cli \
    --accounting-entries examples/accounting_entries_large.csv \
    --list-of-accounts data/accounts/pcg.csv \
    --template data/mappings/detailed_income_statement_pcg.csv \
    --view detailed \
    --period last-month \
    --output out_last_month.csv
```

#### 3) Custom period

```bash
python -m smb_finsight.cli \
    --accounting-entries examples/accounting_entries_large.csv \
    --list-of-accounts data/accounts/pcg.csv \
    --template data/mappings/detailed_income_statement_pcg.csv \
    --from-date 2025-03-01 \
    --to-date 2025-04-15 \
    --view simplified \
    --output out_custom.csv
```

### Example (detailed view)

```bash
python -m smb_finsight.cli \
  --accounting-entries examples/accounting_entries_large.csv \
  --template data/mappings/detailed_income_statement_pcg.csv \
  --list-of-accounts data/accounts/pcg.csv \
  --view detailed \
  --output examples/out_detailed.csv
```

### Example (complete view)

```bash
python -m smb_finsight.cli \
  --accounting-entries examples/accounting_entries_large.csv \
  --template data/mappings/detailed_income_statement_pcg.csv \
  --list-of-accounts data/accounts/pcg.csv \
  --view complete \
  --output examples/out_complete.csv
```

### Example: SIG (Soldes Intermédiaires de Gestion)

```bash
python -m smb_finsight.cli \
  --accounting-entries examples/accounting_entries_large.csv \
  --template data/mappings/sig_pcg.csv \
  --list-of-accounts data/accounts/pcg.csv \
  --view sig \
  --output examples/out_sig.csv
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

## SIG View (PCG)

SMB FinSight provides a full French-style SIG (Soldes Intermédiaires de Gestion)
based on the PCG.

- View: `sig`  
- Mapping file: `data/mappings/sig_pcg.csv`  
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

The SIG result is identical to:
- the result from the detailed view, and  
- the raw sum of all 6* and 7* accounting entries.

This consistency is enforced by test `test_sig_consistency.py`.


---

## 🔢 FinSight Sign Convention

| Element | Debit | Credit | Result |
|--------|--------|---------|--------|
| Expenses (6*) | + | – | negative |
| Revenues (7*) | – | + | positive |

Formula rule:  
`Result = Revenues + Expenses`

---

## 📤 Output Format

All generated CSVs follow the **same column order**:

```csv
display_order,id,level,name,type,amount
```

---

## 🧪 Quick Tests

Run all automated tests and static checks:
```bash
pytest -q
ruff check src tests
ruff format --check src tests
```

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

### ✅ Completed (as of v0.1.5)
- [x] Full PCG mapping engine (levels 0 → 3)
- [x] Complete income statement view (level 4 account details)
- [x] SIG (Soldes Intermédiaires de Gestion) view
- [x] List-of-accounts validation with error detection
- [x] Handling of debit/credit or signed-amount input formats
- [x] Mandatory accounting entry fields: `date`, `code`, `description`
- [x] Fiscal year configuration via `smb_finsight_config.toml`
- [x] Period selection:
  - [x] FY (full fiscal year)
  - [x] YTD (year-to-date)
  - [x] MTD (month-to-date)
  - [x] last-month
  - [x] last-fy
  - [x] custom from/to dates
- [x] Period-based filtering of accounting entries
- [x] Accurate aggregation and recalculation after filtering
- [x] Full test suite (20 tests) including period logic

### 🚧 In Progress
- [ ] 

### 🧭 Planned
- [ ] Add **projected** accounting entries.
- [ ] Introduce **financial ratios**.
- [ ] Extend compatibility to **ASPE (Canada)**.
- [ ] Extend compatibility to **US GAAP / IFRS**.
- [ ] Improve CLI options (output formats, filters)
- [ ] Add **database** feature (save **history** / **current** accounting entries)
- [ ] Add interactive visual reports.  

---

## 🕒 Version History

| Version | Date | Highlights | Tag |
|----------|------|-------------|------|
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
