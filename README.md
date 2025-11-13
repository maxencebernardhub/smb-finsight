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
- [Input Files](#-input-files)
- [CLI Usage](#-cli-usage)
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
- 🧱 Supports **4 views**:  
  - **simplified** → levels ≤ 1  
  - **regular** → levels ≤ 2  
  - **detailed** → levels ≤ 3  
  - **complete** → full mapping + automatic listing of individual account codes from the PCG  
- 🧰 Validates imported account codes using a user-provided **list_of_accounts** file (`pcg.csv`).
- 💾 Exports hierarchical income statements with columns:  
  `display_order, id, level, name, type, amount` as a CSV file.

---

## 📁 Project Structure

```
smb-finsight/
│
├── data/
│   ├── mappings/
│   │   ├── detailed_income_statement_pcg.csv
│   │   └── legacy/
│   │       ├── simplified_income_statement_pcg.csv
│   │       └── regular_income_statement_pcg.csv
│   └── accounts/
│       └── pcg.csv
│
├── examples/
│   ├── accounting_entries.csv
│   ├── accounting_entries_large.csv
│   ├── out_detailed.csv
│   └── out_complete.csv
│
├── src/
│   └── smb_finsight/
│       ├── __init__.py
│       ├── cli.py
│       ├── io.py
│       ├── mapping.py
│       ├── engine.py
│       ├── views.py
│       └── accounts.py
│
└── pyproject.toml
```

🗂️ Legacy mappings (simplified, regular) are preserved under /data/mappings/legacy/ for reference only.

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

## 🖋️ Input Files

### 1. `accounting_entries.csv`

```csv
date,account,debit,credit
2024-12-31,62201,533.25,0
2024-12-31,75402,0,844.65
```

Behavior:

- `amount = credit − debit`
- Class 6 → negative  
- Class 7 → positive

---

### 2. `pcg.csv` (required)

This file **must** list all valid account codes (PCG or custom user chart of accounts):

```csv
account,name
701000,Ventes de produits finis
706000,Prestations de services
62201,Hono…
…
```

Used to:

- Validate imported entries  
- Ignore unknown codes with a console message:  
  `Unknown account code XXXXX ignored`
- Attach accounts automatically in **complete** view

---

## 🧮 CLI Usage

### Base command

```bash
python -m smb_finsight.cli     --accounting_entries <path>     --template data/mappings/detailed_income_statement_pcg.csv     --list-of-accounts data/accounts/pcg.csv     --view <simplified|regular|detailed|complete>     --output <output.csv>
```

### Example (detailed view)

```bash
python -m smb_finsight.cli   --accounting_entries examples/accounting_entries_large.csv   --template data/mappings/detailed_income_statement_pcg.csv   --list-of-accounts data/accounts/pcg.csv   --view detailed   --output examples/out_detailed.csv
```

### Example (complete view)

```bash
python -m smb_finsight.cli   --accounting_entries examples/accounting_entries_large.csv   --template data/mappings/detailed_income_statement_pcg.csv   --list-of-accounts data/accounts/pcg.csv   --view complete   --output examples/out_complete.csv
```

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

### ✅ Completed
- [x] Core aggregation engine (v0.1.0)
- [x] CLI interface (`smb-finsight`)
- [x] CI/CD pipeline (Ruff + Pytest)
- [x] Adding inline comments and docstrings to improve code readability.
- [x] Account validation
- [x] Mapping template (Simplified, Regular, Detailed and Complete view)
- [x] Full PCG multi-level format
- [x] SUM(; ) support 

### 🚧 In Progress
- [ ] 

### 🧭 Planned
- [ ] Generate Intermediate Management Balances (aka SIG in PCG) automatically.
- [ ] Add **dates** and **periods**.
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
| **0.1.3** | Nov 2025 | Unified mapping, new CLI, complete income statement view | [v0.1.3](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.3) |
| **0.1.2** | Nov 2025 | Internal documentation update | [v0.1.2](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.2) |
| **0.1.1** | Nov 2025 | Updated README (CI badge, contributing), CI improvements | [v0.1.1](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.1) |
| **0.1.0** | Nov 2025 | Initial release: core engine, mappings, CLI, tests | [v0.1.0](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.0) |

---

## 📜 License

MIT License © Maxence Bernard  
See [`LICENSE`](LICENSE) for details.
