# RELand Backend API Test Commands

Base URL: `http://127.0.0.1:5001` (or your deployed URL)

## Quick Test Script

Run all tests at once:
```bash
chmod +x test_api.sh
./test_api.sh
# Or with custom URL:
./test_api.sh http://your-backend-url.com
```

---

## Individual curl Commands

### 1. API Root - Health Check
```bash
curl -X GET http://127.0.0.1:5001/
```

### 2. Get Initial Data (Available Areas)
```bash
curl -X GET http://127.0.0.1:5001/api/initial_data
```

### 3. Get Map Data (Single Area)
```bash
curl -X GET "http://127.0.0.1:5001/api/map_data?areas[]=ABEJORRAL"
```

### 4. Get Map Data (Multiple Areas)
```bash
curl -X GET "http://127.0.0.1:5001/api/map_data?areas[]=ABEJORRAL&areas[]=SONSÓN"
```

### 5. Get All User Labels
```bash
curl -X GET http://127.0.0.1:5001/api/labels
```

### 6. Add/Update Label
```bash
curl -X POST http://127.0.0.1:5001/api/labels \
  -H "Content-Type: application/json" \
  -d '{
    "location_id": 1,
    "label": 1
  }'
```

### 7. Delete Label
```bash
curl -X DELETE http://127.0.0.1:5001/api/labels/1
```

### 8. Get All Confirmed Events
```bash
curl -X GET http://127.0.0.1:5001/api/confirmed_events
```

### 9. Add Confirmed Event
```bash
curl -X POST http://127.0.0.1:5001/api/confirmed_events \
  -H "Content-Type: application/json" \
  -d '{
    "location_id": 1,
    "event_type": "landmine",
    "date": "2024-01-15",
    "notes": "Test event"
  }'
```

### 10. Update Confirmed Event
```bash
curl -X PUT http://127.0.0.1:5001/api/confirmed_events/1 \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "landmine",
    "date": "2024-01-16",
    "notes": "Updated test event"
  }'
```

### 11. Delete Confirmed Event
```bash
curl -X DELETE http://127.0.0.1:5001/api/confirmed_events/1
```

### 12. Get Municipality Borders
```bash
curl -X GET http://127.0.0.1:5001/api/municipality_borders
```

### 13. Geocode Address
```bash
curl -X GET "http://127.0.0.1:5001/api/geocode?address=Bogota, Colombia"
```

### 14. Update Single Location Risk Score
```bash
curl -X PUT http://127.0.0.1:5001/api/locations/1 \
  -H "Content-Type: application/json" \
  -d '{
    "risk_score": 0.75,
    "risk_score_lr": 0.68,
    "risk_level": "High"
  }'
```

### 15. Bulk Update Risk Scores
```bash
curl -X POST http://127.0.0.1:5001/api/locations/bulk_update \
  -H "Content-Type: application/json" \
  -d '{
    "updates": [
      {"location_id": 1, "risk_score": 0.75, "risk_score_lr": 0.68, "risk_level": "High"},
      {"location_id": 2, "risk_score": 0.45, "risk_score_lr": 0.42, "risk_level": "Medium"}
    ]
  }'
```

### 16. Recalculate and Predict (Model Inference)
```bash
curl -X POST http://127.0.0.1:5001/api/recalculate_and_predict \
  -H "Content-Type: application/json" \
  -d '{
    "experiment_timestamp": "11242025142747"
  }'
```

### 17. Retrain Model
```bash
curl -X POST http://127.0.0.1:5001/api/retrain_model \
  -H "Content-Type: application/json" \
  -d '{
    "municipio": "blockCV",
    "subset": "full",
    "model": "MLP_IRM",
    "objective": "irm",
    "n_step": 2
  }'
```

### 18. Get Job Status
```bash
curl -X GET http://127.0.0.1:5001/api/job_status/YOUR_JOB_ID
```

### 19. Get All Jobs
```bash
curl -X GET http://127.0.0.1:5001/api/jobs
```

---

## Pretty Print with jq

For better formatted JSON output, pipe to `jq`:
```bash
curl -X GET http://127.0.0.1:5001/api/initial_data | jq '.'
```

---

## Testing with Different Base URLs

### Local Development
```bash
BASE_URL="http://127.0.0.1:5001"
curl -X GET $BASE_URL/api/initial_data
```

### AWS Deployment (replace with your actual URL)
```bash
BASE_URL="https://your-backend.elasticbeanstalk.com"
curl -X GET $BASE_URL/api/initial_data
```

---

## Expected Response Examples

### Initial Data Response
```json
{
  "areas": ["ABEJORRAL", "SONSÓN", "blockCV", ...]
}
```

### Map Data Response
```json
[
  {
    "id": 1,
    "lat": 5.789,
    "lon": -75.432,
    "municipio": "ABEJORRAL",
    "risk_score": 0.75,
    "risk_score_lr": 0.68,
    "risk_level": "High",
    ...
  },
  ...
]
```

### Label Response
```json
{
  "message": "Label added/updated successfully",
  "location_id": 1,
  "label": 1
}
```

### Confirmed Event Response
```json
{
  "id": 1,
  "location_id": 1,
  "event_type": "landmine",
  "date": "2024-01-15",
  "notes": "Test event",
  "created_at": "2024-01-15T10:30:00"
}
```

---

## Notes

- All endpoints support CORS
- POST/PUT requests require `Content-Type: application/json` header
- Location IDs and Event IDs are integers
- Date format: `YYYY-MM-DD`
- Label values: `0` (negative) or `1` (positive)
- Event types: `"landmine"`, `"suspected"`, etc.











