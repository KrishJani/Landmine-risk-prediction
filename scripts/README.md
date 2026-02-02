# Scripts

Run from **project root** (e.g. `python scripts/run_checks.py`).

| Script | Purpose |
|--------|---------|
| `run_checks.py` | DB + CSV checks (locations per municipio, distinct coords) |
| `diagnose_causes.py` | Diagnose uniform risk: coordinate mismatch, feature variation, model output |
| `csv_labels_check.py` | Print mines_outcome label counts per municipality (resolution_0.5.csv) |
| `deploy-helper.sh` | AWS deployment helper (ECR, App Runner, etc.) |

For `diagnose_causes.py` check 3 (model output), use the backend venv:  
`cd reland-backend && source venv/bin/activate && cd .. && python scripts/diagnose_causes.py`
