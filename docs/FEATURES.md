# RELand — Application Features

This document lists the main features of the RELand (Landmine Risk Prediction) application in plain language, with brief technical notes where helpful. It is written for both technical and non-technical readers.

---

## 1. React Frontend (replacing Dash)

**What it means:** The web interface was rebuilt from Dash (Python) to **React** with **Mapbox GL** for the map. Users get a fast, interactive map in the browser.

**Technical:** React S3 + CloudFront; Mapbox GL JS for rendering and interactions.

---

## 2. PostgreSQL Database (replacing SQLite/CSV)

**What it means:** All map data, labels, and confirmed events are stored in **PostgreSQL** instead of files or SQLite. The app uses **SQLAlchemy** to talk to the database, which improves reliability and supports multiple users.

**Technical:** PostgreSQL + PostGIS on RDS; SQLAlchemy ORM models.

---

## 3. User Labeling

**What it means:** Users can **label locations** on the map as:
- **Mine-free (0)** or **Confirmed mine (1)**  
and add optional notes. Labels are saved and shown on the map.

**Technical:** REST API: `GET/POST /api/labels`; `DELETE /api/labels/<location_id>`.

---

## 4. Confirmed Events Management

**What it means:** Confirmed mine events can be **created, viewed, updated, and deleted**. Each event can store location, date, description, and **source** (where the information came from).

**Technical:** CRUD API: `GET/POST /api/confirmed_events`, `PUT/DELETE /api/confirmed_events/<id>`; optional filter by municipality.

---

## 5. Municipality Borders on the Map

**What it means:** **Municipality boundaries** are drawn on the map as polygons, so users can see which area they are looking at. Data comes from shapefiles converted to GeoJSON.

**Technical:** `GET /api/municipality_borders` (or static GeoJSON in the frontend); GeoJSON polygons.

---

## 6. Address Search (Geocoding)

**What it means:** Users can **search by address** (e.g. “Bogotá, Colombia”). The app finds the coordinates and **moves the map** to that place so they can navigate quickly.

**Technical:** `GET /api/geocode?address=...`; Google Geocoding API.

---

## 7. Distance Recalculation

**What it means:** When **new confirmed events** are added, the app can **recompute the distance from every location to the nearest confirmed event**. Those distances are used in risk predictions, so the map stays up to date.

**Technical:** `POST /api/recalculate_and_predict` triggers recalculation and optional re-prediction.

---

## 8. Bulk Location Updates

**What it means:** After re-running the prediction model (e.g. after retraining), **risk scores for many locations** can be updated in one go instead of one-by-one.

**Technical:** `POST /api/locations/bulk_update`; optional `PUT /api/locations/<id>` for a single location.

---

## 9. Custom Map Markers

**What it means:**  
- **Predictions:** Shown with **square markers**, **color-coded by risk** (e.g. green = low, yellow = medium, red = high).  
- **Confirmed events:** Shown with **triangle markers** (e.g. red) so they are easy to tell apart from predictions.

**Technical:** Mapbox symbol layers with custom SVG icons; risk level drives icon type/color.

---

## 10. Interactive Tooltips

**What it means:** When you **hover over a point** on the map, a **tooltip** appears with details (e.g. location, risk, coordinates). From the tooltip you can **quickly add or edit a label** without opening a separate screen.

**Technical:** Map hover events; tooltip component with “Add label” / “Edit label” actions.

---

## 11. Map Style Switching

**What it means:** Users can **switch the base map style** to better match their needs:
- **Street** — standard road map  
- **Satellite Streets** — satellite imagery with street labels  
- **Outdoors** — terrain and outdoor-oriented view  

**Technical:** Mapbox styles: `streets-v11`, `satellite-streets-v11`, `outdoors-v11`.

---

## 12. Top-Down Map View

**What it means:** The map is kept in a **fixed top-down view** (no tilt, north up). This gives a **consistent 2D view** of risk and events, which is easier for analysis and reporting.

**Technical:** Fixed `pitch: 0`, `bearing: 0` in the map viewport.

---

## 13. Confirmed Events Panel

**What it means:** A **side panel** lists **all confirmed events** with key details (location, date, description, etc.). From the panel, users can **edit or delete** events without clicking on the map.

**Technical:** Frontend panel; data from `GET /api/confirmed_events`; edit/delete call existing API endpoints.

---

## 14. Manual Coordinate Entry

**What it means:** Users can **add labels or confirmed events** by **typing latitude and longitude** instead of only clicking on the map. Useful when coordinates come from external sources or reports.

**Technical:** Forms for labels and events include optional lat/lon fields; same APIs as map-based entry.

---

## 15. Database Initialization Script

**What it means:** On **first setup**, an automated script (**init_database.py**) loads initial data (e.g. from CSV) into PostgreSQL so the app has locations and risk data ready to use without manual SQL.

**Technical:** `init_database.py` in reland-backend; reads CSV (e.g. risk_map_predictions.csv) and populates Location (and related) tables.

---

## 16. Area / Municipality Selection

**What it means:** Users can **choose which municipalities (areas)** to show on the map via a **dropdown**. Only data for the selected areas is loaded, which keeps the map fast and focused.

**Technical:** `GET /api/initial_data` for the list of areas; `GET /api/map_data?areas[]=...` for map data; multi-select in the UI.

---

## 17. Layer Toggles

**What it means:** Users can **turn layers on or off** so they can focus on what they need:
- **Predictions** (risk heatmap and/or square markers)  
- **Historical / user labels**  
- **Clusters** (if used)  
- **Confirmed events** (triangles)  
- **Municipality borders**  

**Technical:** Mapbox layer visibility toggles in the sidebar; data layers rendered in a defined order.

---

## 18. Risk Heatmap and Point Display

**What it means:** Risk can be shown in two ways (depending on implementation): as a **heatmap** (smooth color gradients by risk level) and/or as **individual points** (square markers by risk). This helps both overview and detailed inspection.

**Technical:** Mapbox heatmap layer + symbol layer; risk score normalized for color/icon.

---

## 19. Model Retraining and Re-prediction (AWS)

**What it means:** Retrain the risk model or re-run predictions on demand; training and prediction run as background jobs on **fully AWS-deployed** infrastructure (e.g. EC2 worker), with job status and last-trained model visible in the app.

**Technical:** `POST /api/retrain_model`; `GET /api/job_status/<job_id>`; `GET /api/jobs`; `GET /api/last_trained_model`; async training service (e.g. EC2 Spot).

---

## 20. Export Predictions

**What it means:** Download current prediction data (and confirmed events) as **Excel (.xlsx)** or **GeoJSON** for use in spreadsheets or GIS tools.

**Technical:** `GET /api/export_predictions` with format (e.g. default Excel, `?format=geojson` for GeoJSON).

---

## 21. Health Check

**What it means:** A health endpoint lets load balancers and monitoring tools verify that the backend is up and responding.

**Technical:** `GET /health` (or similar) returns a simple OK/status response.

---

## 22. Map Legend

**What it means:** A **legend** on the map explains what the colors and symbols mean (e.g. low/medium/high risk, confirmed events). This helps new users and non-technical stakeholders understand the map at a glance.

**Technical:** Sidebar or overlay component describing layers and marker types.

---

## 23. Reset View and Advanced Actions

**What it means:** Users can **reset the map view** (e.g. back to default center and zoom). Additional actions (e.g. **Recalculate**, **Retrain**) are grouped in an expandable “More actions” section so the main controls stay simple.

**Technical:** Reset viewport to initial state; collapsible UI section for recalculate/retrain and related options.

---

## Summary Table

| # | Feature | For users | Technical hook |
|---|---------|-----------|----------------|
| 1 | React + Mapbox frontend | New fast, interactive map UI | React, Mapbox GL JS |
| 2 | PostgreSQL database | Reliable, multi-user data storage | PostgreSQL, SQLAlchemy |
| 3 | User labeling | Mark locations as mine-free or confirmed mine, with notes | `/api/labels` |
| 4 | Confirmed events CRUD | Add, edit, delete confirmed events; track source | `/api/confirmed_events` |
| 5 | Municipality borders | See boundaries on the map | `/api/municipality_borders`, GeoJSON |
| 6 | Address geocoding | Search by address and jump to location | `/api/geocode`, Google Geocoding |
| 7 | Distance recalculation | Update distances and predictions when events change | `/api/recalculate_and_predict` |
| 8 | Bulk location updates | Update many risk scores after re-prediction | `/api/locations/bulk_update` |
| 9 | Custom markers | Squares for risk, triangles for confirmed events | Mapbox symbol layers |
| 10 | Hover tooltips | See details and add/edit labels from tooltip | Map hover + tooltip UI |
| 11 | Map style switch | Street, Satellite Streets, Outdoors | Mapbox styles |
| 12 | Top-down view | Fixed 2D, north-up map | pitch: 0, bearing: 0 |
| 13 | Confirmed events panel | List, edit, delete events in a side panel | Panel + `/api/confirmed_events` |
| 14 | Manual coordinates | Enter lat/lon to add labels or events | Label and event forms |
| 15 | DB init script | Load CSV into DB on first setup | `init_database.py` |
| 16 | Area selection | Choose which municipalities to show | `/api/initial_data`, `/api/map_data` |
| 17 | Layer toggles | Show/hide predictions, labels, events, borders | Layer visibility in UI |
| 18 | Heatmap + points | Risk as heatmap and/or colored points | Heatmap + symbol layers |
| 19 | Retrain / re-predict (AWS) | Retrain or re-run predictions on demand; fully AWS-deployed, job status in app | `/api/retrain_model`, `/api/job_status`, `/api/jobs`, `/api/last_trained_model` |
| 20 | Export | Download predictions and events as Excel or GeoJSON | `/api/export_predictions` |
| 21 | Health check | Backend liveness for load balancers and monitoring | `/health` |
| 22 | Legend | Explains colors and symbols on the map | Legend component |
| 23 | Reset & more actions | Reset map; recalculate/retrain in one place | Viewport reset, “More actions” UI |

---

*Last updated: February 2026*
