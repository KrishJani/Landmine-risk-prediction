#!/usr/bin/env python3
"""
Diagnose the 3 possible causes of uniform risk per municipality:
1. Coordinate mismatch (many DB points map to same CSV point)
2. Features nearly constant per municipality in CSV
3. Model outputs nearly constant per municipality

Run from project root: python scripts/diagnose_causes.py
Uses: stdlib + psql for DB; for check 3 needs reland-backend venv (see bottom).
"""
import csv
import argparse
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict

# Project root (parent of scripts/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(PROJECT_ROOT, 'reland-backend', '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Numeric columns used by EventDB subset='full' (from dataset_db.py)
NUMERIC_COLS_FULL = [
    'airports_dist', 'seaport_dist', 'settlement_dist', 'finance_dist', 'edu_dist',
    'buildings_dist', 'waterways_dist', 'rwi', 'elevation', 'roads_dist',
    'No. Víctimas por Declaración', 'retro_pobl_tot', 'indrural', 'dist_old_mine',
    'areaoficialkm2', 'altura', 'discapital', 'pib_percapita_cons', 'hist_mines',
    'rainfall', 'temperature', 'dist_roads_t1', 'dist_roads_t2', 'dist_roads_t3',
    'population_2012', 'coca_dist', 'soil_texture15_trans1', 'soil_texture15_trans2',
    'nighttime_lights_2012', 'dist_pipeline', 'dist_powerline', 'dist_telecom', 'dist_mining',
    'forest_gain', 'forest_loss',
    '0.5km_hist_mines', '2.0km_hist_mines', '8.0km_hist_mines', '16.0km_hist_mines', '32.0km_hist_mines',
    'animal_inc', 'animal_dec'
]

FOCUS_MUNICIPALITIES = ['CARTAGENA DE INDIAS', 'PUERTO LIBERTADOR', 'CÓRDOBA', 'SAN JUAN NEPOMUCENO', 'SANTA ROSA DEL SUR', 'ZAMBRANO']


def get_db_locations_by_municipio():
    """Return dict: municipio -> list of (lon, lat)."""
    db_url = os.getenv('LOCAL_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not db_url or not db_url.startswith('postgresql://'):
        return None
    out = defaultdict(list)
    for m in FOCUS_MUNICIPALITIES:
        try:
            r = subprocess.run(
                ['psql', db_url, '-t', '-A', '-F', ',', '-c',
                 f"SELECT lon, lat FROM locations WHERE municipio = '{m.replace(chr(39), chr(39)+chr(39))}';"],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode != 0 or not r.stdout.strip():
                continue
            for line in r.stdout.strip().splitlines():
                parts = line.split(',', 1)
                if len(parts) == 2:
                    try:
                        lon, lat = float(parts[0]), float(parts[1])
                        out[m].append((lon, lat))
                    except ValueError:
                        pass
        except Exception:
            pass
    return dict(out) if out else None


def check_1_coordinate_mismatch(db_by_municipio, csv_path):
    """Check: for each municipality, how many unique CSV rows do DB points map to?"""
    print("=" * 60)
    print("CHECK 1: Coordinate mismatch (DB -> nearest CSV row)")
    print("=" * 60)
    if not db_by_municipio:
        print("  Skipped: no DB locations (set LOCAL_DATABASE_URL and run psql).\n")
        return
    if not os.path.exists(csv_path):
        print(f"  Skipped: CSV not found at {csv_path}\n")
        return
    # Load CSV rows with (LONGITUD_X, LATITUD_Y) and Municipio
    with open(csv_path, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)
    mcol = 'Municipio' if csv_rows and 'Municipio' in csv_rows[0] else 'municipio'
    lon_col, lat_col = 'LONGITUD_X', 'LATITUD_Y'
    if not csv_rows or lon_col not in csv_rows[0] or lat_col not in csv_rows[0]:
        print("  CSV missing LONGITUD_X/LATITUD_Y or Municipio.\n")
        return
    # Build per-municipio CSV point lists (index in full CSV, lon, lat)
    csv_by_municipio = defaultdict(list)
    for i, r in enumerate(csv_rows):
        try:
            lon = float(r.get(lon_col, 0))
            lat = float(r.get(lat_col, 0))
            m = r.get(mcol, '')
            if m:
                csv_by_municipio[m].append((i, lon, lat))
        except (ValueError, TypeError):
            pass
    for m in FOCUS_MUNICIPALITIES:
        db_pts = db_by_municipio.get(m, [])
        csv_pts = csv_by_municipio.get(m, [])
        if not db_pts or not csv_pts:
            print(f"  {m!r}: no DB or CSV points, skip.")
            continue
        # For each DB point, find nearest CSV point (same municipio) by Euclidean distance
        nearest_csv_indices = []
        for (db_lon, db_lat) in db_pts:
            best_idx, best_d2 = None, float('inf')
            for (csv_i, csv_lon, csv_lat) in csv_pts:
                d2 = (db_lon - csv_lon) ** 2 + (db_lat - csv_lat) ** 2
                if d2 < best_d2:
                    best_d2, best_idx = d2, csv_i
            if best_idx is not None:
                nearest_csv_indices.append(best_idx)
        # Count: how many unique CSV indices? How many DB points per CSV index?
        n_db = len(nearest_csv_indices)
        n_unique_csv = len(set(nearest_csv_indices))
        counts = Counter(nearest_csv_indices)
        max_db_per_csv = max(counts.values()) if counts else 0
        print(f"  {m!r}:")
        print(f"    DB points: {n_db}, unique CSV rows hit: {n_unique_csv}, max DB points per CSV row: {max_db_per_csv}")
        if n_unique_csv == 1 and n_db > 1:
            print(f"    >>> CAUSE 1 LIKELY: all {n_db} DB points map to the SAME CSV row.")
        elif n_unique_csv < n_db / 10:
            print(f"    >>> CAUSE 1 POSSIBLE: many DB points map to few CSV rows.")
        else:
            print(f"    Coordinate mapping looks fine (many unique CSV rows).")
    print()


def check_2_feature_variation(csv_path):
    """Check: per municipality, do numeric features vary (std > 0)?"""
    print("=" * 60)
    print("CHECK 2: Feature variation per municipality (resolution_0.5.csv)")
    print("=" * 60)
    if not os.path.exists(csv_path):
        print(f"  CSV not found: {csv_path}\n")
        return
    with open(csv_path, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        print("  Empty CSV.\n")
        return
    mcol = 'Municipio' if 'Municipio' in rows[0] else 'municipio'
    # Which numeric cols exist in CSV
    sample = rows[0]
    numeric_cols = [c for c in NUMERIC_COLS_FULL if c in sample]
    if not numeric_cols:
        print("  No numeric columns from EventDB list found in CSV. Sample keys:", list(sample.keys())[:20])
        print()
        return
    by_municipio = defaultdict(list)
    for r in rows:
        m = r.get(mcol, '')
        if m:
            by_municipio[m].append(r)
    for m in FOCUS_MUNICIPALITIES:
        rlist = by_municipio.get(m, [])
        if not rlist:
            print(f"  {m!r}: no rows, skip.")
            continue
        n = len(rlist)
        zero_std_cols = []
        for col in numeric_cols:
            vals = []
            for r in rlist:
                try:
                    v = r.get(col, '')
                    if v != '':
                        vals.append(float(v))
                except (ValueError, TypeError):
                    pass
            if len(vals) < 2:
                zero_std_cols.append(col)
                continue
            mean = sum(vals) / len(vals)
            variance = sum((x - mean) ** 2 for x in vals) / len(vals)
            std = math.sqrt(variance)
            if std < 1e-10:
                zero_std_cols.append(col)
        print(f"  {m!r}: {n} rows, {len(numeric_cols)} numeric cols checked, {len(zero_std_cols)} with zero/near-zero std")
        if len(zero_std_cols) == len(numeric_cols):
            print(f"    >>> CAUSE 2 LIKELY: all numeric features constant in this municipality.")
        elif len(zero_std_cols) > len(numeric_cols) // 2:
            print(f"    >>> CAUSE 2 POSSIBLE: many constant features. Zero-std cols (sample): {zero_std_cols[:8]}")
        else:
            print(f"    Features vary (few constant cols).")
    print()


def check_3_model_output(model_name='Lightweight', municipio='map_included', timestamp=None, subset='full'):
    """Check: does the model output vary per municipality? Requires backend env."""
    print("=" * 60)
    print("CHECK 3: Model output variation per municipality")
    print("=" * 60)
    sys.path.insert(0, PROJECT_ROOT)
    sys.path.insert(0, os.path.join(PROJECT_ROOT, 'reland-backend'))
    os.chdir(PROJECT_ROOT)
    db_url = os.getenv('LOCAL_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not db_url:
        print("  Set LOCAL_DATABASE_URL in reland-backend/.env and re-run.\n")
        return
    try:
        import numpy as np
    except ImportError:
        print("  numpy not found. Run from backend venv: cd reland-backend && source venv/bin/activate && cd .. && python scripts/diagnose_causes.py\n")
        return
    try:
        from dataset_db import EventDB
    except ImportError as e:
        print(f"  EventDB import failed: {e}. Run from project root with PYTHONPATH including backend.\n")
        return
    try:
        from utils.train_municipios_loader import load_train_municipios_for_repredict
        val_municipio = 'ALL' if municipio in ['blockCV', 'map_included'] else municipio.upper()
        train_municipios = load_train_municipios_for_repredict(timestamp, municipio)
        # Load full dataset (val_municipio='ALL' -> all rows)
        all_data = EventDB(
            train_municipios=train_municipios,
            val_municipio=val_municipio,
            subset=subset,
            split='val',
            db_url=db_url
        )
    except Exception as e:
        print(f"  EventDB load failed: {e}\n")
        return
    # We need municipio per row; EventDB doesn't expose it. Get from CSV directly: same row order as merged data.
    csv_path = os.path.join(PROJECT_ROOT, 'processed_dataset', 'resolution_0.5.csv')
    if not os.path.exists(csv_path):
        print("  resolution_0.5.csv not found; cannot map rows to municipio.\n")
        return
    with open(csv_path, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)
    mcol = 'Municipio' if csv_rows and 'Municipio' in csv_rows[0] else 'municipio'
    # EventDB order: when val_municipio='ALL', val_tabX = tabX (all rows), so order is same as CSV
    if len(csv_rows) != len(all_data):
        print(f"  Row count mismatch: CSV={len(csv_rows)}, EventDB={len(all_data)}. Check EventDB merge.\n")
        return
    municipio_per_row = [r.get(mcol, '') for r in csv_rows]
    # Load a model (Lightweight/sklearn is easiest)
    try:
        from utils.model_finder import ModelFinder
        from pathlib import Path
    except ImportError:
        print("  ModelFinder not found. Run from backend env.\n")
        return
    if timestamp:
        exp_dir = Path(PROJECT_ROOT) / 'experiments' / timestamp
        ext = '.pkl' if model_name not in ['TabCmpt', 'MLP'] else '.pth'
        fold_paths = sorted(list(exp_dir.glob(f'*{ext}')))
    else:
        timestamp, fold_paths = ModelFinder.find_all_fold_models_in_latest_experiment(model_name, municipio)
        if not fold_paths:
            model_path, _, _ = ModelFinder.find_latest_model(model_name, municipio)
            fold_paths = [model_path] if model_path else []
    if not fold_paths:
        print(f"  No {model_name} model found in experiments/ for municipio={municipio}.\n")
        return
    import pickle
    try:
        with open(fold_paths[0], 'rb') as f:
            model = pickle.load(f)
    except Exception as e:
        print(f"  Failed to load model: {e}\n")
        return
    tabX = np.array(all_data.tabX, dtype=np.float64)
    if np.any(np.isnan(tabX)):
        tabX = np.nan_to_num(tabX, nan=0.0, posinf=0.0, neginf=0.0)
    try:
        preds = model.predict_proba(tabX)[:, 1]
    except Exception as e:
        print(f"  predict_proba failed: {e}\n")
        return
    preds = np.asarray(preds).flatten()
    by_mun = defaultdict(list)
    for i, m in enumerate(municipio_per_row):
        if m and i < len(preds):
            by_mun[m].append(float(preds[i]))
    for m in FOCUS_MUNICIPALITIES:
        vals = by_mun.get(m, [])
        if not vals:
            print(f"  {m!r}: no predictions, skip.")
            continue
        n = len(vals)
        mean = sum(vals) / n
        variance = sum((x - mean) ** 2 for x in vals) / n
        std = math.sqrt(variance)
        min_p, max_p = min(vals), max(vals)
        print(f"  {m!r}: n={n}, mean={mean:.4f}, std={std:.6f}, min={min_p:.4f}, max={max_p:.4f}")
        if std < 1e-6:
            print(f"    >>> CAUSE 3 LIKELY: model outputs constant ({mean:.4f}) for this municipality.")
        elif max_p - min_p < 0.01:
            print(f"    >>> CAUSE 3 POSSIBLE: model output almost constant.")
        else:
            print(f"    Model output varies.")
    print()


if __name__ == '__main__':
    # For Check 3 (model output) you need pandas/sklearn/sqlalchemy. Run with backend venv:
    #   cd reland-backend && source venv/bin/activate && cd .. && python scripts/diagnose_causes.py
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='Lightweight', help='Model type, e.g. Lightweight | TabCmpt')
    parser.add_argument('--municipio', default='map_included', help='Split name from train_val_stream, e.g. map_included | blockCV')
    parser.add_argument('--timestamp', default=None, help='Optional experiment timestamp to force')
    parser.add_argument('--subset', default='full', help='Feature subset used by model, e.g. full | geo | single')
    args = parser.parse_args()

    csv_path = os.path.join(PROJECT_ROOT, 'processed_dataset', 'resolution_0.5.csv')
    db_locations = get_db_locations_by_municipio()
    check_1_coordinate_mismatch(db_locations, csv_path)
    check_2_feature_variation(csv_path)
    check_3_model_output(
        model_name=args.model,
        municipio=args.municipio,
        timestamp=args.timestamp,
        subset=args.subset
    )
    print("Done.")
