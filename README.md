# RELand - Landmine Risk Prediction System

A machine learning system for predicting landmine risk in Colombia using geospatial data and historical events.

## 🚀 Production Deployment

**For production deployment to AWS:**

👉 **[DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)** - Complete step-by-step deployment guide

**Cost Target:** ~$38.95/month (optimized, no Redis)

## 🏗️ Architecture

- **Frontend:** React app on S3 + CloudFront
- **Backend:** Flask API on AWS App Runner
- **Database:** PostgreSQL with PostGIS on RDS
- **Training:** EC2 Spot instances (g4dn.xlarge GPU)
- **Storage:** S3 for models and static files

## 💰 Cost Breakdown

| Component | Cost/Month |
|-----------|-----------|
| Frontend (S3 + CloudFront) | $0.50 |
| Backend (App Runner) | $15.00 |
| Database (RDS) | $17.00 |
| Model Training (EC2 Spot) | $5.20 |
| Model Storage (S3) | $1.15 |
| Artifacts (ECR) | $0.10 |
| **TOTAL** | **~$38.95** |

## 🔧 Local Development

See [reland-backend/README.md](./reland-backend/README.md) for local setup.

## 📝 License

See [LICENSE](./LICENSE) file.
