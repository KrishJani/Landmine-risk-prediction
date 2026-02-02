# RELand Backend

Flask REST API backend for the RELand landmine risk prediction system. This backend has been refactored to follow SOLID principles with a clean, maintainable architecture.

## 🚀 Quick Start

### Local Development

1. **Set up PostgreSQL database:**
   - Install PostgreSQL (if not already installed)
   - Create database and user:
   ```sql
   CREATE DATABASE reland_db;
   CREATE USER reland_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE reland_db TO reland_user;
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and set your LOCAL_DATABASE_URL for local development
   ```
   
   **Important:** For local development, use `LOCAL_DATABASE_URL`:
   ```bash
   LOCAL_DATABASE_URL=postgresql://reland_user:your_password@localhost:5432/reland_db
   ```
   
   The backend will automatically use `LOCAL_DATABASE_URL` when running locally. 
   `DATABASE_URL` is reserved for production (RDS) and will only be used when `FLASK_ENV=production`.

3. **Create and activate virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Initialize database:**
   ```bash
   python init_database.py
   ```
   This creates tables and loads data from CSV files into PostgreSQL (one-time setup).

6. **Run the server:**
   ```bash
   python app.py
   ```
   The server will start on `http://127.0.0.1:5001` (or the port specified in `.env`).

### Production

Set the following environment variables in your deployment platform:
- `DATABASE_URL` - PostgreSQL connection string to RDS (required)
- `GOOGLE_GEOCODING_API_KEY` - Google API key (optional)
- `FLASK_ENV=production` - Set to production mode
- `PORT` - Port number (usually set by platform)

**Important:** In production, the backend uses `DATABASE_URL` (which should point to RDS).
`LOCAL_DATABASE_URL` is ignored in production mode.

The application will automatically use `ProductionConfig` when `FLASK_ENV=production`.

## 📁 Project Structure

```
reland-backend/
├── app.py                      # Main Flask application
├── config.py                   # Configuration management
├── exceptions.py               # Custom exception classes
├── models.py                   # Database models
├── wsgi.py                     # WSGI entry point for production
│
├── services/                   # Business logic layer
│   ├── location_service.py     # Location operations
│   ├── label_service.py        # Label operations
│   ├── event_service.py        # Event operations
│   ├── map_service.py          # Map data operations
│   └── training_service.py      # Training job operations
│
├── routes/                     # HTTP request handlers
│   ├── health.py               # Health check endpoint
│   ├── initial_data.py         # Initial data endpoint
│   ├── map_data.py             # Map data endpoint
│   ├── geocode.py              # Geocoding endpoint
│   ├── labels.py               # Label management
│   ├── events.py               # Event management
│   ├── locations.py           # Location management
│   ├── training.py            # Training jobs
│   ├── recalculate.py         # Recalculate and predict
│   └── municipality_borders.py # Municipality borders
│
├── utils/                      # Utility modules
    ├── risk_calculator.py      # Risk level calculations
    ├── distance_calculator.py  # Distance calculations
    ├── model_finder.py         # Model file finding
    └── geocoding.py            # Geocoding service
│
├── docs/                       # Legacy deployment/troubleshooting notes
└── scripts/                    # Deploy/diagnose helper scripts (.sh)
```

## 🔌 API Endpoints

### Core Endpoints
- `GET /` - API information
- `GET /health` - Health check
- `GET /api/initial_data` - Get list of available areas
- `GET /api/map_data?areas[]=<area1>&areas[]=<area2>` - Get map data
- `GET /api/geocode?address=<address>` - Geocode an address
- `GET /api/municipality_borders?municipalities[]=<name>` - Get municipality borders

### Label Management
- `GET /api/labels` - Get all user labels
- `POST /api/labels` - Add or update a label
  ```json
  {
    "location_id": 123,
    "label": 1,
    "notes": "Optional notes"
  }
  ```
- `DELETE /api/labels/<location_id>` - Delete a label

### Confirmed Events
- `GET /api/confirmed_events?municipio=<name>` - Get all confirmed events (optionally filtered)
- `POST /api/confirmed_events` - Add a confirmed event
- `PUT /api/confirmed_events/<id>` - Update a confirmed event
- `DELETE /api/confirmed_events/<id>` - Delete a confirmed event

### Location Updates
- `PUT /api/locations/<id>` - Update a single location's risk score
- `POST /api/locations/bulk_update` - Bulk update risk scores

### Model Training
- `POST /api/retrain_model` - Retrain the model (creates async job)
- `GET /api/job_status/<job_id>` - Get training job status
- `GET /api/jobs` - List recent training jobs
- `POST /api/recalculate_and_predict` - Recalculate distances and re-predict

### Example API Calls

**Get initial data:**
```bash
curl -X GET http://127.0.0.1:5001/api/initial_data
```

**Get map data (single area):**
```bash
curl -X GET "http://127.0.0.1:5001/api/map_data?areas[]=ABEJORRAL"
```

**Get map data (multiple areas):**
```bash
curl -X GET "http://127.0.0.1:5001/api/map_data?areas[]=ABEJORRAL&areas[]=SONSÓN"
```

**Get all user labels:**
```bash
curl -X GET http://127.0.0.1:5001/api/labels
```

**Add or update a label:**
```bash
curl -X POST http://127.0.0.1:5001/api/labels \
  -H "Content-Type: application/json" \
  -d '{"location_id": 1, "label": 1, "notes": "Test"}'
```

**Delete a label:**
```bash
curl -X DELETE http://127.0.0.1:5001/api/labels/1
```

**Get all confirmed events:**
```bash
curl -X GET http://127.0.0.1:5001/api/confirmed_events
```

**Get confirmed events filtered by municipio:**
```bash
curl -X GET "http://127.0.0.1:5001/api/confirmed_events?municipio=ABEJORRAL"
```

**Add a confirmed event:**
```bash
curl -X POST http://127.0.0.1:5001/api/confirmed_events \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 5.789,
    "lon": -75.432,
    "municipio": "ABEJORRAL",
    "event_date": "2024-01-15",
    "description": "Test event",
    "source": "manual"
  }'
```

**Update a confirmed event:**
```bash
curl -X PUT http://127.0.0.1:5001/api/confirmed_events/1 \
  -H "Content-Type: application/json" \
  -d '{"description": "Updated event description"}'
```

**Delete a confirmed event:**
```bash
curl -X DELETE http://127.0.0.1:5001/api/confirmed_events/1
```

**Update location risk score:**
```bash
curl -X PUT http://127.0.0.1:5001/api/locations/1 \
  -H "Content-Type: application/json" \
  -d '{"risk_score": 0.75, "risk_level": "High"}'
```

**Bulk update locations:**
```bash
curl -X POST http://127.0.0.1:5001/api/locations/bulk_update \
  -H "Content-Type: application/json" \
  -d '{
    "locations": [
      {"id": 1, "risk_score": 0.75, "risk_level": "High"},
      {"id": 2, "risk_score": 0.45, "risk_level": "Medium"}
    ]
  }'
```

**Geocode an address:**
```bash
curl -X GET "http://127.0.0.1:5001/api/geocode?address=Bogota, Colombia"
```

**Get municipality borders:**
```bash
curl -X GET "http://127.0.0.1:5001/api/municipality_borders?municipalities[]=ABEJORRAL"
```

**Retrain model:**
```bash
curl -X POST http://127.0.0.1:5001/api/retrain_model \
  -H "Content-Type: application/json" \
  -d '{
    "municipio": "blockCV",
    "subset": "full",
    "model": "TabCmpt",
    "objective": "irm",
    "n_step": 2
  }'
```

**Get job status:**
```bash
curl -X GET http://127.0.0.1:5001/api/job_status/YOUR_JOB_ID
```

**List all jobs:**
```bash
curl -X GET http://127.0.0.1:5001/api/jobs
```

**Recalculate distances and re-predict:**
```bash
curl -X POST http://127.0.0.1:5001/api/recalculate_and_predict \
  -H "Content-Type: application/json" \
  -d '{
    "model": "TabCmpt",
    "municipio": "blockCV",
    "subset": "full",
    "objective": "irm"
  }'
```

## 🏗️ Architecture

The backend follows SOLID principles with a clean architecture:

- **Service Layer**: Business logic separated from HTTP handling
- **Route Handlers**: Thin controllers that delegate to services
- **Utilities**: Reusable helper functions
- **Configuration**: Environment-specific configuration management
- **Exception Handling**: Custom exception hierarchy for better error handling

### SOLID Principles Applied

- **Single Responsibility**: Each class has one clear purpose
- **Open/Closed**: Extensible through inheritance and composition
- **Liskov Substitution**: Config classes are interchangeable
- **Interface Segregation**: Focused service interfaces
- **Dependency Inversion**: Dependencies injected, not hardcoded

### Architecture Overview

The application uses a layered architecture:
- **Routes** → **Services** → **Models** → **Database**
- Each layer has a single responsibility
- Dependencies flow downward (routes depend on services, not vice versa)

## 📊 UML Diagrams

### Class Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Flask Application                        │
│                         (app.py)                                 │
│  + create_app()                                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ uses
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Configuration                           │
│                         (config.py)                             │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │   Config         │  │                  │                   │
│  │  + DATABASE_URL  │◄─┤  LocalConfig     │                   │
│  │  + init_app()    │  │  ProductionConfig│                   │
│  └──────────────────┘  └──────────────────┘                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ provides config to
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Database Models                         │
│                         (models.py)                             │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │   Location   │      │  UserLabel   │      │ConfirmedEvent│  │
│  │  + id        │◄─────┤  + location_id│    │  + location_id│ │
│  │  + lat/lon   │      │  + label     │      │  + lat/lon   │  │
│  │  + to_dict() │      │  + to_dict()│      │  + to_dict() │  │
│  └──────┬───────┘      └──────────────┘      └──────┬───────┘  │
│         │                                            │          │
│         └────────────────────────────────────────────┘          │
│                           │                                     │
│                  ┌────────▼────────┐                            │
│                  │  TrainingJob   │                            │
│                  │  + id         │                            │
│                  │  + status     │                            │
│                  │  + to_dict()  │                            │
│                  └─────────────────┘                            │
└────────────────────────────┬────────────────────────────────────┘
                             │ used by
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Service Layer                           │
│                      (services/)                                │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │ LocationService │  │  LabelService    │                   │
│  │  + get_all()    │  │  + get_all()    │                   │
│  │  + get_by_id()  │  │  + create_or_   │                   │
│  │  + update()     │  │    update()     │                   │
│  └──────────────────┘  └──────────────────┘                   │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │  EventService    │  │  MapService      │                   │
│  │  + get_all()    │  │  + get_map_data()│                   │
│  │  + create()     │  │                  │                   │
│  └──────────────────┘  └──────────────────┘                   │
│  ┌──────────────────┐                                         │
│  │ TrainingService  │                                         │
│  │  + create_job()  │                                         │
│  │  + get_job()     │                                         │
│  └──────────────────┘                                         │
└────────────────────────────┬───────────────────────────────────┘
                             │ uses
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Utilities                               │
│                      (utils/)                                   │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │ RiskCalculator  │  │DistanceCalculator│                   │
│  │  + calculate_    │  │  + distance_to_  │                   │
│  │    risk_levels() │  │    closest_point()│                   │
│  └──────────────────┘  └──────────────────┘                   │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │  ModelFinder     │  │ GeocodingService │                   │
│  │  + find_latest_  │  │  + geocode_      │                   │
│  │    model()       │  │    address()     │                   │
│  └──────────────────┘  └──────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             │ used by
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Route Handlers                          │
│                      (routes/)                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ initial_data │  │  map_data    │  │   geocode    │         │
│  │  + get_      │  │  + get_      │  │  + geocode_  │         │
│  │    initial_  │  │    map_data()│  │    address() │         │
│  │    data()    │  │              │  │              │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   labels     │  │    events    │  │  locations   │         │
│  │  + get_      │  │  + get_      │  │  + update()  │         │
│  │    labels()  │  │    events()  │  │              │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐                           │
│  │   training   │  │ recalculate  │                           │
│  │  + retrain_  │  │  + recalc_  │                           │
│  │    model()   │  │    predict() │                           │
│  └──────────────┘  └──────────────┘                           │
└────────────────────────────┬───────────────────────────────────┘
                             │ raises
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Exceptions                              │
│                      (exceptions.py)                            │
│  ┌──────────────────┐                                          │
│  │ RELandException   │                                          │
│  │  + message        │                                          │
│  │  + status_code    │                                          │
│  │  + to_dict()      │                                          │
│  └────────┬─────────┘                                          │
│           │                                                     │
│  ┌────────┴─────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ DatabaseError     │  │ValidationError│  │NotFoundError │    │
│  └──────────────────┘  └──────────────┘  └──────────────┘    │
│  ┌──────────────────┐  ┌──────────────┐                       │
│  │   ModelError      │  │ConfigError   │                       │
│  └──────────────────┘  └──────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      RELand Backend API                          │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                    HTTP Layer                             │ │
│  │  (Flask Routes - Blueprints)                              │ │
│  │  - health, initial_data, map_data, geocode                │ │
│  │  - labels, events, locations, training                     │ │
│  └────────────────────┬─────────────────────────────────────┘ │
│                       │                                        │
│  ┌────────────────────▼─────────────────────────────────────┐ │
│  │                 Service Layer                              │ │
│  │  - LocationService                                        │ │
│  │  - LabelService                                           │ │
│  │  - EventService                                           │ │
│  │  - MapService                                             │ │
│  │  - TrainingService                                        │ │
│  └────────────────────┬─────────────────────────────────────┘ │
│                       │                                        │
│  ┌────────────────────▼─────────────────────────────────────┐ │
│  │                 Utility Layer                              │ │
│  │  - RiskCalculator                                         │ │
│  │  - DistanceCalculator                                     │ │
│  │  - ModelFinder                                            │ │
│  │  - GeocodingService                                       │ │
│  └────────────────────┬─────────────────────────────────────┘ │
│                       │                                        │
│  ┌────────────────────▼─────────────────────────────────────┐ │
│  │                 Data Access Layer                          │ │
│  │  (SQLAlchemy ORM - models.py)                             │ │
│  │  - Location, UserLabel, ConfirmedEvent, TrainingJob        │ │
│  └────────────────────┬─────────────────────────────────────┘ │
│                       │                                        │
│  ┌────────────────────▼─────────────────────────────────────┐ │
│  │                 Database                                   │ │
│  │  PostgreSQL (RDS)                                          │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                 External Services                          │ │
│  │  - Google Geocoding API                                   │ │
│  │  - AWS EC2 (for training)                                 │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Sequence Diagram - Adding a Label

```
User          Route Handler      LabelService      LocationService    Database
 │                  │                  │                  │              │
 │ POST /api/labels │                  │                  │              │
 ├─────────────────>│                  │                  │              │
 │                  │                  │                  │              │
 │                  │ create_or_update│                  │              │
 │                  ├─────────────────>│                  │              │
 │                  │                  │                  │              │
 │                  │                  │ _find_or_create  │              │
 │                  │                  ├─────────────────>│              │
 │                  │                  │                  │              │
 │                  │                  │                  │ query        │
 │                  │                  │                  ├─────────────>│
 │                  │                  │                  │              │
 │                  │                  │                  │<─────────────┤
 │                  │                  │                  │              │
 │                  │                  │<──────────────────┤              │
 │                  │                  │                  │              │
 │                  │                  │ save label       │              │
 │                  │                  ├─────────────────────────────────>│
 │                  │                  │                  │              │
 │                  │                  │<─────────────────────────────────┤
 │                  │                  │                  │              │
 │                  │<─────────────────┤                  │              │
 │                  │                  │                  │              │
 │<─────────────────┤                  │                  │              │
 │                  │                  │                  │              │
```

### Sequence Diagram - Getting Map Data

```
Frontend      Route Handler      MapService      LocationService    EventService    Database
   │                 │                 │                 │               │              │
   │ GET /api/map_data│                 │                 │               │              │
   ├─────────────────>│                 │                 │               │              │
   │                 │                 │                 │               │              │
   │                 │ get_map_data()  │                 │               │              │
   │                 ├────────────────>│                 │               │              │
   │                 │                 │                 │               │              │
   │                 │                 │ get_by_municipios│              │              │
   │                 │                 ├─────────────────>│              │              │
   │                 │                 │                 │              │              │
   │                 │                 │                 │ query        │              │
   │                 │                 │                 ├──────────────>│              │
   │                 │                 │                 │              │              │
   │                 │                 │                 │<──────────────┤              │
   │                 │                 │                 │              │              │
   │                 │                 │<─────────────────┤              │              │
   │                 │                 │                 │              │              │
   │                 │                 │ get_all()       │              │              │
   │                 │                 ├─────────────────────────────────>│              │
   │                 │                 │                 │               │              │
   │                 │                 │                 │               │ query        │
   │                 │                 │                 │               ├─────────────>│
   │                 │                 │                 │               │              │
   │                 │                 │                 │               │<─────────────┤
   │                 │                 │                 │               │              │
   │                 │                 │<─────────────────────────────────┤              │
   │                 │                 │                 │               │              │
   │                 │                 │ calculate_risk_levels()         │              │
   │                 │                 │ (uses RiskCalculator)            │              │
   │                 │                 │                 │               │              │
   │                 │<────────────────┤                 │               │              │
   │                 │                 │                 │               │              │
   │<────────────────┤                 │                 │               │              │
   │                 │                 │                 │               │              │
```

### Package/Module Diagram

```
reland-backend/
│
├── app.py ──────────────┐
│                        │ imports
├── config.py ───────────┼───┐
│                        │   │
├── exceptions.py ───────┼───┼───┐
│                        │   │   │
├── models.py ───────────┼───┼───┼───┐
│                        │   │   │   │
├── services/            │   │   │   │
│   ├── location_service │───┼───┼───┼───┐
│   ├── label_service    │───┼───┼───┼───┼───┐
│   ├── event_service    │───┼───┼───┼───┼───┼───┐
│   ├── map_service      │───┼───┼───┼───┼───┼───┼───┐
│   └── training_service │───┼───┼───┼───┼───┼───┼───┼───┐
│                        │   │   │   │   │   │   │   │   │
├── routes/              │   │   │   │   │   │   │   │   │
│   ├── initial_data ────┼───┼───┼───┼───┼───┼───┼───┼───┼───┐
│   ├── map_data ────────┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┐
│   ├── labels ──────────┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┐
│   ├── events ──────────┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┐
│   ├── locations ───────┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┐
│   ├── training ────────┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┐
│   └── recalculate ─────┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┐
│                        │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │
└── utils/               │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │
    ├── risk_calculator  │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │
    ├── distance_calc    │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │
    ├── model_finder     │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │
    └── geocoding        │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │
                         │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │
                         ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼
                    All modules import from: models, exceptions, config, utils
```

### Relationship Summary

**Inheritance Relationships:**
- `LocalConfig` → `Config`
- `ProductionConfig` → `Config`
- `DatabaseError`, `ValidationError`, `NotFoundError`, `ModelError`, `ConfigurationError` → `RELandException`

**Composition Relationships:**
- `Location` has many `UserLabel` (one-to-many)
- `Location` has optional `ConfirmedEvent` (one-to-many)
- Services contain references to Models

**Dependency Relationships:**
- Routes depend on Services
- Services depend on Models and Utils
- Services depend on Database (via SQLAlchemy)
- Routes depend on Exceptions (for error handling)

**Association Relationships:**
- `MapService` uses `LocationService` and `EventService`
- `LabelService` uses `LocationService` (for finding/creating locations)
- `TrainingService` uses AWS EC2 helper (external dependency)

#### Design Patterns Used

1. **Factory Pattern**: `create_app()` function creates Flask app instance
2. **Repository Pattern**: Services act as repositories for data access
3. **Service Layer Pattern**: Business logic separated from routes
4. **Strategy Pattern**: Different config classes for different environments
5. **Exception Hierarchy**: Custom exceptions for better error handling
6. **Dependency Injection**: Configuration and services injected rather than hardcoded

## 🗄️ Database

All data is stored in PostgreSQL. CSV files are only used during initial database setup via `init_database.py`.

### Database Schema

#### Tables

1. **locations** - Risk prediction locations with features and scores
   - `id` (Primary Key)
   - `lat`, `lon` (Coordinates)
   - `municipio` (Municipality name)
   - `risk_score`, `risk_score_lr` (Risk scores)
   - `risk_level` (Low/Medium/High)
   - `elevation`, `rainfall`, `temperature`, `population_2012`, `hist_mines` (Features)
   - `dist_old_mine` (Distance to closest confirmed event in km)
   - `created_at`, `updated_at` (Timestamps)

2. **user_labels** - User-assigned labels (0 = mine-free, 1 = confirmed mine)
   - `id` (Primary Key)
   - `location_id` (Foreign Key to locations)
   - `label` (0 or 1)
   - `notes` (Optional user notes)
   - `user_id` (For future multi-user support)
   - `created_at`, `updated_at` (Timestamps)

3. **confirmed_events** - Confirmed mine events
   - `id` (Primary Key)
   - `lat`, `lon` (Coordinates)
   - `municipio`, `departamento` (Location info)
   - `event_date` (Date of the event)
   - `description` (Event description)
   - `source` (manual, user_label, EO_events)
   - `location_id` (Optional foreign key to locations)
   - `eo_event_id` (If imported from EO_events)
   - `created_at`, `updated_at` (Timestamps)

4. **training_jobs** - Model training job tracking
   - `id` (Primary Key, UUID or timestamp-based)
   - `job_type` (retrain or repredict)
   - `status` (pending, running, completed, failed)
   - `municipio`, `subset`, `model_name`, `objective`, `n_step` (Job parameters)
   - `progress` (0.0 to 1.0)
   - `progress_message` (Status message)
   - `result` (JSON string with results)
   - `error_message` (Error details if failed)
   - `ec2_instance_id` (EC2 instance tracking)
   - `created_at`, `started_at`, `completed_at` (Timestamps)

### Database Usage

**Adding Labels:**
1. User clicks point on map → Frontend sends label to backend
2. Backend saves to `user_labels` table via `LabelService`
3. Labels are stored with location_id, label (0 or 1), and optional notes
4. If location doesn't exist, it's created automatically

**Managing Events:**
- Confirmed events are stored in `confirmed_events` table
- Can be created manually via API or from user labels
- Events include location (lat/lon), municipio, date, description, and source
- Events can be filtered by municipio when querying

**Data Flow:**
- **Initial Load**: CSV files → Database (via `init_database.py`)
- **Runtime**: All data comes from PostgreSQL database
- **Map Display**: Locations and events loaded from database via services
- **Labels**: Stored in database, linked to locations via foreign key
- **Training Jobs**: Tracked in database for async job management

**Troubleshooting:**

- **Database not found**: Run `init_database.py` to create tables
- **Labels not saving**: Check backend is running and database connection is correct
- **Events not showing**: Verify events exist in database and municipio filter is correct
- **Connection errors**: Check `DATABASE_URL` in `.env` matches your PostgreSQL setup

## 🔧 Configuration

### Environment Variables

**Local Development** (`.env` file):
```env
DATABASE_URL=postgresql://reland_user:password@localhost:5432/reland_db
GOOGLE_GEOCODING_API_KEY=your_api_key
FLASK_ENV=local
PORT=5001
DEBUG=True
```

**Production** (set as environment variables in deployment platform):
```env
DATABASE_URL=postgresql://user:password@host:5432/reland_db
GOOGLE_GEOCODING_API_KEY=your_production_key
FLASK_ENV=production
PORT=8080
DEBUG=False
```

> **Note**: In production, environment variables are set directly in your deployment platform (AWS App Runner, Docker, etc.). Do NOT use `.env` files in production for security reasons.

See `.env.example` for a template.

## 🧪 Testing

Run the refactoring test suite:
```bash
python test_refactored_app.py
```

This verifies that all modules can be imported and the app structure is correct.

## 🐛 Error Handling

The backend uses a custom exception hierarchy:

- `RELandException` - Base exception
- `DatabaseError` - Database-related errors (500)
- `ValidationError` - Input validation errors (400)
- `NotFoundError` - Resource not found errors (404)
- `ModelError` - Model-related errors (500)
- `ConfigurationError` - Configuration errors (500)

All exceptions return JSON responses with error details.

## 📚 Additional Information

### Response Examples

**Initial Data Response:**
```json
{
  "areas": ["ABEJORRAL", "SONSÓN", "blockCV", ...]
}
```

**Map Data Response:**
```json
{
  "risk_heatmap_points": [
    {
      "LATITUD_Y": 5.789,
      "LONGITUD_X": -75.432,
      "risk_score": 0.75,
      "risk_level": "High",
      "color": "rgb(255, 0, 0)",
      "location_id": 1,
      "Municipio": "ABEJORRAL"
    }
  ],
  "historical_points": [...],
  "confirmed_events": [...]
}
```

**Label Response:**
```json
{
  "id": 1,
  "location_id": 1,
  "label": 1,
  "notes": "Test",
  "created_at": "2024-01-15T10:30:00"
}
```

**Confirmed Event Response:**
```json
{
  "id": 1,
  "lat": 5.789,
  "lon": -75.432,
  "municipio": "ABEJORRAL",
  "event_date": "2024-01-15",
  "description": "Test event",
  "source": "manual",
  "created_at": "2024-01-15T10:30:00"
}
```

### Notes

- All endpoints support CORS
- POST/PUT requests require `Content-Type: application/json` header
- Location IDs and Event IDs are integers
- Date format: `YYYY-MM-DD` or ISO format
- Label values: `0` (mine-free) or `1` (confirmed mine)
- Event source: `"manual"`, `"user_label"`, `"EO_events"`, etc.
- For more details, see code comments and docstrings in service and route files

## 🚢 Deployment

### How Environment Differentiation Works

**Key Principle**: The same Docker image works for both local and production. Environment variables differentiate environments at **runtime**, not build time.

```
Single Docker Image → Runtime Environment Variables → Config Selection
                     ↓                              ↓
              FLASK_ENV=local              LocalConfig
              FLASK_ENV=production         ProductionConfig
```

### Local Development with Docker

**Option 1: Docker Compose (Recommended)**
```bash
docker-compose up --build
```
See `docker-compose.yml` for configuration. Sets `FLASK_ENV=local` automatically.

**Option 2: Docker Run**
```bash
docker build -t reland-backend .
docker run -p 5001:5001 \
  -e FLASK_ENV=local \
  -e DATABASE_URL=postgresql://user:pass@host.docker.internal:5432/reland_db \
  -e PORT=5001 \
  reland-backend
```

**Option 3: Using .env file**
```bash
docker run -p 5001:5001 --env-file .env -e FLASK_ENV=local reland-backend
```

### Production Deployment (AWS App Runner)

The same Docker image is pushed to ECR and deployed to App Runner. Environment variables are set in App Runner service configuration:

- `FLASK_ENV=production` → Uses `ProductionConfig`
- `DATABASE_URL` → From AWS Secrets Manager or environment variables
- `PORT` → Set by App Runner (usually 8080)

**No `.env` file needed in production** - all configuration comes from environment variables set by the platform.

### Building and Pushing to ECR

```bash
# Build (same image for all environments)
docker build -t reland-backend:latest .

# Tag for ECR
docker tag reland-backend:latest \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/reland-backend:latest

# Push to ECR
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/reland-backend:latest
```

The deployment workflow (`.github/workflows/deploy-backend.yml`) automatically:
1. Builds the Docker image
2. Pushes to ECR
3. Updates App Runner with new image
4. Sets production environment variables

### Using WSGI (Gunicorn, uWSGI, etc.)

```bash
gunicorn wsgi:application --bind 0.0.0.0:5001
```

The `wsgi.py` file provides the WSGI entry point for production servers.

### Environment Variables Summary

| Variable | Local | Production |
|----------|-------|------------|
| `FLASK_ENV` | `local` | `production` |
| `DATABASE_URL` | Local PostgreSQL | RDS endpoint |
| `PORT` | `5001` | `8080` |
| `DEBUG` | `True` | `False` |
| Config Source | `.env` file | Environment variables |

For detailed Docker deployment information, see the Docker section above.

## 🔄 Migration from Old Code

If you're migrating from the old `backend-app.py`:

1. Update imports: Change `from backend_app import app` to `from app import app`
2. Update environment: Copy `.env.example` to `.env` and configure your local database URL
3. All API endpoints remain unchanged - no client code changes needed

The old `backend-app.py` is kept for reference but should not be used.

## ✅ Verification

Run the verification script to ensure everything is set up correctly:
```bash
python verify_setup.py
```

This checks:
- All imports work correctly
- Flask app structure is correct
- All routes are registered
- Configuration detection works
- Services have required methods
- Utilities have required methods

The verification script checks all critical components and reports any issues.

## 📝 License

See the main project [LICENSE](../LICENSE) file.

## 🤝 Contributing

1. Follow the existing code structure and SOLID principles
2. Add tests for new features
3. Update documentation as needed
4. Ensure all API endpoints remain backward compatible
