# RELand Backend - Local Development Guide

This guide explains how to run the RELand backend locally with background job processing for model training.

## Architecture

The backend consists of two services:
1. **Web Service**: Flask API that handles HTTP requests
2. **Worker Service**: Background worker that processes long-running model training jobs

Both services use Redis for job queuing.

## Prerequisites

- PostgreSQL database (for application data)
- Redis instance (for job queue)
- Python 3.11+ environment

## Environment Variables

Required environment variables (create a `.env` file in `reland-backend/`):

```bash
DATABASE_URL=postgresql://user:password@host:port/database
REDIS_URL=redis://localhost:6379/0
FLASK_ENV=development
```

## Local Development Setup

### 1. Install Dependencies

```bash
cd reland-backend
source venv/bin/activate  # or create a new venv
pip install -r requirements.txt
```

### 2. Start Redis

**macOS (Homebrew):**
```bash
brew install redis
brew services start redis
```

**Linux:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

**Docker:**
```bash
docker run -d -p 6379:6379 redis:latest
```

**Verify Redis is running:**
```bash
redis-cli ping
# Should return: PONG
```

### 3. Start the Backend

**Terminal 1 - Web Server:**
```bash
cd reland-backend
source venv/bin/activate
python backend-app.py
```

**Terminal 2 - Worker:**
```bash
cd reland-backend
source venv/bin/activate
python worker.py
```

The backend will be available at `http://localhost:5001`

## API Endpoints

### Submit Training Job

```bash
POST /api/retrain_model
Content-Type: application/json

{
  "municipio": "blockCV",
  "subset": "full",
  "model": "TabCmpt",
  "objective": "irm",
  "n_step": 2
}
```

**Response:**
```json
{
  "message": "Model training job submitted successfully",
  "job_id": "abc123...",
  "status": "queued",
  "status_url": "/api/job_status/abc123..."
}
```

### Check Job Status

```bash
GET /api/job_status/<job_id>
```

**Response:**
```json
{
  "job_id": "abc123...",
  "status": "started",
  "progress": "Training model (this may take 5-30 minutes)...",
  "created_at": "2024-01-01T12:00:00",
  "started_at": "2024-01-01T12:00:05"
}
```

**Status values:**
- `queued`: Job is waiting to be processed
- `started`: Job is currently running
- `finished`: Job completed successfully
- `failed`: Job failed with an error

### List Recent Jobs

```bash
GET /api/jobs
```

## Monitoring

### Check Worker Status

The worker logs will show:
- Job start/completion
- Progress updates
- Errors

### Check Redis Queue

```bash
redis-cli
> LLEN rq:queue:model_training  # Number of queued jobs
> KEYS rq:job:*  # List all jobs
```

## Troubleshooting

### "Redis not available"

- Ensure Redis is running: `redis-cli ping` should return `PONG`
- Check `REDIS_URL` environment variable
- For local dev, use `redis://localhost:6379/0`

### "Job not found"

- Jobs expire after 24 hours (result_ttl=86400)
- Check Redis is persistent (not in-memory only)
- Verify worker is running and processing jobs

### "Worker not processing jobs"

- Check worker logs for errors
- Verify Redis connection
- Ensure worker has access to ML dependencies (torch, etc.)

### "Model training fails"

- Check worker logs for detailed error messages
- Verify Python interpreter has ML dependencies
- Ensure `main.py` and training data are accessible
- Check database connection from worker

## Frontend Integration

Update your React frontend to handle async job submission:

```javascript
// Submit training job
const response = await fetch('http://localhost:5001/api/retrain_model', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    municipio: 'blockCV',
    subset: 'full',
    model: 'TabCmpt',
    objective: 'irm'
  })
});

const { job_id, status_url } = await response.json();

// Poll for job status
const checkStatus = async () => {
  const statusResponse = await fetch(`http://localhost:5001${status_url}`);
  const status = await statusResponse.json();
  
  if (status.status === 'finished') {
    console.log('Training completed!', status.result);
  } else if (status.status === 'failed') {
    console.error('Training failed:', status.error);
  } else {
    console.log('Status:', status.status, status.progress);
    // Poll again after 5 seconds
    setTimeout(checkStatus, 5000);
  }
};

checkStatus();
```

## Production Considerations

1. **Scaling Workers**: Run multiple worker processes for parallel training
2. **Job Timeout**: Adjust `job_timeout` in `retrain_model` endpoint if needed
3. **Result Retention**: Jobs expire after 24 hours; adjust `result_ttl` if needed
4. **Monitoring**: Set up logging/monitoring for both web and worker services
5. **Resource Limits**: Ensure workers have enough CPU/memory for model training

