# RELand — Landmine Risk Prediction

ML system for predicting landmine risk in Colombia using geospatial data and historical events.

## Project structure

```
Landmine-risk-prediction/
├── main.py              # Training entry (models, train/val, save experiments)
├── dataset_db.py        # Database-backed dataset (EventDB)
├── save_predictions_db.py  # Save predictions to PostgreSQL
├── model.py, reland.py, loss.py, utils.py   # ML components
├── run_predictions.sh   # Run predictions with DB (set DATABASE_URL)
├── run_reland.sh        # Example training run
│
├── docs/                # Project documentation
│   ├── HANDOVER_GUIDE.md    # Start here for handover
│   ├── AWS_ARCHITECTURE_EXPLAINED.md
│   ├── DEPLOY_AFTER_CHANGE.md
│   ├── CODE_OVERVIEW.md
│   ├── DATA_ARCHITECTURE.md
│   ├── MANUAL_DEPLOYMENT_AWS_CONSOLE.md  # Deploy via AWS website step-by-step
│   └── DEPLOYMENT_DETAILED_DOCUMENTATION.md
├── scripts/             # Utilities (run from project root)
│   ├── deploy_reland.sh    # Deploy frontend/backend/DB (--frontend, --backend, --database)
│   ├── run_checks.py       # DB + CSV checks
│   ├── diagnose_causes.py  # Diagnose uniform-risk causes
│   ├── csv_labels_check.py # Label counts per municipality
│   └── deploy-helper.sh    # AWS deployment helper
│
├── reland-backend/      # Flask API (see reland-backend/README.md)
├── reland-frontend/     # React map UI
└── pytorch_tabnet_irm/  # TabNet IRM model code
```

## Quick start

- **Local backend:** See [reland-backend/README.md](reland-backend/README.md).
- **Training:** Set `LOCAL_DATABASE_URL` (or `DATABASE_URL`), then e.g. `./run_predictions.sh` or `python main.py --help`.
- **Scripts:** From project root: `python scripts/run_checks.py`, `python scripts/diagnose_causes.py`, `python scripts/csv_labels_check.py`.

## Architecture

- **Frontend:** React on S3 + CloudFront  
- **Backend:** Flask on AWS App Runner  
- **Database:** PostgreSQL + PostGIS on RDS  
- **Training:** EC2 Spot (g4dn.xlarge) or local worker  

**Handover:** See [docs/HANDOVER_GUIDE.md](docs/HANDOVER_GUIDE.md) for the professor handover (architecture, deploy-after-change, code overview, data sources).  
See [docs/](docs/) for data architecture and deployment details.

## License

See [LICENSE](LICENSE).
