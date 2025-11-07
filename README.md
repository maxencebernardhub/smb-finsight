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
- [Installation (Local)](#-installation-local)
- [CLI Usage](#-cli-usage)
- [Quick Tests](#-quick-tests)
- [Contributing](#-contributing)
- [Roadmap](#-roadmap)
- [Version History](#-version-history)
- [License](#-license)

---

## ⚙️ Main Features

- 📂 Reads an `accounting_entries.csv` file containing debit/credit postings.  
- 📊 Aggregates data automatically according to a selected mapping (`simplified` or `regular`).  
- 🧮 Applies pre-defined calculation formulas (`Products + Charges`) after sign normalization.  
- 💾 Exports a hierarchical **Income Statement** as a CSV file.  
- 🧰 Modular and extensible architecture — ready for IFRS / ASPE extensions.

---

## 📁 Project Structure

```
smb-finsight/
│
├── data/
│   └── mappings/
│       ├── simplified_income_statement_pcg.csv
│       └── regular_income_statement_pcg.csv
│
├── examples/
│   ├── accounting_entries.csv
│   ├── out_simplified.csv
│   └── out_regular.csv
│
├── src/
│   └── smb_finsight/
│       ├── __init__.py
│       ├── cli.py
│       ├── io.py
│       ├── mapping.py
│       └── engine.py
│
└── pyproject.toml
```

---

## 🧩 Installation (Local)

```bash
git clone https://github.com/<your-account>/smb-finsight.git
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

## 🖋️ Input File

### `examples/accounting_entries.csv`

```csv
date,account,debit,credit
2024-12-31,62201,533.25,0
2024-12-31,75402,0,844.65
```

- Columns `debit` and `credit` are **required**.  
- The engine computes `amount = credit − debit`.  
- As a result:
  - **Expenses (class 6)** → negative amounts  
  - **Revenues (class 7)** → positive amounts

---

## 🧮 CLI Usage

### Simplified Income Statement
```bash
python -m smb_finsight.cli   --accounting_entries examples/accounting_entries.csv   --template data/mappings/simplified_income_statement_pcg.csv   --output examples/out_simplified.csv
```

### Regular Income Statement
```bash
python -m smb_finsight.cli   --accounting_entries examples/accounting_entries.csv   --template data/mappings/regular_income_statement_pcg.csv   --output examples/out_regular.csv
```

---

## 📤 Example Output

**File:** `examples/out_simplified.csv`
```csv
level,display_order,id,name,type,amount
0,110,11,Net income,calc,311.4
1,10,1,Operating revenues,acc,844.65
1,20,2,Operating expenses,acc,-533.25
1,30,3,Operating income,calc,311.4
```

---

## 🔢 FinSight Sign Convention

| Element | Debit | Credit | Computed amount (`credit − debit`) |
|----------|--------|---------|-----------------------------------|
| **Expenses (class 6)** | positive (debit) | negative (credit) | negative amount |
| **Revenues (class 7)** | negative (debit) | positive (credit) | positive amount |

**Formula convention:**  
> `Result = Revenues + Expenses`  
> (since expenses are negative after normalization)

---

## ✅ Available Mappings

| Mapping | Description | Main Formula |
|----------|--------------|---------------|
| **Simplified** | Condensed version of income statement (classes 6 & 7) | `=Revenues + Expenses` |
| **Regular** | Full PCG income statement with main sections | `=Revenues + Expenses` |

---

## 🧪 Quick Tests

```bash
pytest -q
```

Tests validate:
- correct formula evaluation (`=1+2`, `=7+14`, etc.);
- proper aggregation of account ranges;
- consistency of computed totals in generated CSVs.

Run Ruff checks and formatting validation:

```bash
ruff check src tests
ruff format --check src tests
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

### ✅ Completed
- [x] Core aggregation engine (v0.1.0)
- [x] CLI interface (`smb-finsight`)
- [x] Mapping templates (Simplified & Regular PCG)
- [x] CI/CD pipeline (Ruff + Pytest)

### 🚧 In Progress
- [ ] Adding inline comments and docstrings to improve code readability.

### 🧭 Planned
- [ ] Add **detailed** mapping (full PCG multi-level format).
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
| 0.1.1 | Nov 2025 | Updated README (CI badge, contributing), CI improvements | [v0.1.1](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.1) |
| 0.1.0 | Nov 2025 | Initial release: core engine, mappings, CLI, tests | [v0.1.0](https://github.com/maxencebernardhub/smb-finsight/releases/tag/v0.1.0) |

---

## 📜 License

MIT License © Maxence Bernard  
See [`LICENSE`](LICENSE) for details.
