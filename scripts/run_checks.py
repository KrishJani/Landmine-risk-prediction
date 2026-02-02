#!/usr/bin/env python3
"""
Run DB and CSV checks to diagnose uniform risk per municipality.
Run from project root: python scripts/run_checks.py

Uses only stdlib for CSV; DB uses psql if available, else prints SQL to run.
"""
import csv
import os
import subprocess
import sys
from collections import Counter, defaultdict

# Project root (parent of scripts/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Load .env from reland-backend
env_path = os.path.join(PROJECT_ROOT, 'reland-backend', '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def db_checks():
    """Run PostgreSQL checks: try psql, else print SQL."""
    db_url = os.getenv('LOCAL_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not db_url:
        print("⚠️  No LOCAL_DATABASE_URL or DATABASE_URL set. Skipping DB checks.")
        print("   Set in reland-backend/.env or run the SQL below manually.\n")
        _print_db_sql()
        return
    # Parse URL for psql: postgresql://user:pass@host:port/dbname
    if not db_url.startswith('postgresql://'):
        print("⚠️  DATABASE_URL not in postgresql:// form. Run the SQL below manually.\n")
        _print_db_sql()
        return
    try:
        # psql -c "SELECT ..." requires connection string
        result = subprocess.run(
            ['psql', db_url, '-t', '-A', '-F', ',', '-c',
             """SELECT municipio, COUNT(*), COUNT(DISTINCT (ROUND(lon::numeric, 6), ROUND(lat::numeric, 6)))
FROM locations GROUP BY municipio ORDER BY municipio;"""],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            print("=" * 60)
            print("DATABASE CHECKS (table: locations)")
            print("=" * 60)
            print("municipio | total_locations | distinct_coords (lon,lat rounded to 6 decimals)\n")
            for line in result.stdout.strip().splitlines():
                parts = line.split(',', 2)
                if len(parts) >= 3:
                    print(f"  {parts[0]!r}: total={parts[1]}, distinct_coords={parts[2]}")
            print()
        else:
            print("⚠️  psql failed or no output. Run the SQL below manually.\n")
            _print_db_sql()
    except FileNotFoundError:
        print("⚠️  psql not found. Run the SQL below manually in your DB client.\n")
        _print_db_sql()
    except Exception as e:
        print(f"⚠️  DB check error: {e}\n")
        _print_db_sql()


def _print_db_sql():
    print("Run this SQL in your PostgreSQL client (psql, DBeaver, etc.):")
    print("-" * 50)
    print("""
SELECT municipio,
       COUNT(*) AS total_locations,
       COUNT(DISTINCT (ROUND(lon::numeric, 6), ROUND(lat::numeric, 6))) AS distinct_coords
FROM locations
GROUP BY municipio
ORDER BY municipio;
""")
    print()


def csv_checks():
    """Run CSV checks using stdlib csv only."""
    # resolution_0.5.csv
    path_res = os.path.join(PROJECT_ROOT, 'processed_dataset', 'resolution_0.5.csv')
    if not os.path.exists(path_res):
        print(f"⚠️  resolution_0.5.csv not found at {path_res}\n")
        return
    print("=" * 60)
    print("CSV: processed_dataset/resolution_0.5.csv (model features)")
    print("=" * 60)
    with open(path_res, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        print("  (empty file)\n")
        return
    mcol = 'Municipio' if 'Municipio' in rows[0] else ('municipio' if 'municipio' in rows[0] else None)
    lon_col = 'LONGITUD_X' if 'LONGITUD_X' in rows[0] else None
    lat_col = 'LATITUD_Y' if 'LATITUD_Y' in rows[0] else None
    if mcol is None:
        print("  Columns (first 15):", list(rows[0].keys())[:15])
    else:
        counts = Counter(r[mcol] for r in rows)
        print("\nRows per municipality:")
        for name in sorted(counts.keys()):
            print(f"  {name!r}: {counts[name]} rows")
        if lon_col and lat_col:
            distinct = defaultdict(set)
            for r in rows:
                try:
                    lon, lat = r.get(lon_col), r.get(lat_col)
                    if lon and lat:
                        key = (round(float(lon), 6), round(float(lat), 6))
                        distinct[r[mcol]].add(key)
                except (ValueError, TypeError):
                    pass
            print("\nDistinct (LONGITUD_X, LATITUD_Y) per municipality:")
            for name in sorted(distinct.keys()):
                print(f"  {name!r}: {len(distinct[name])} distinct coords")
    print(f"  Total rows in CSV: {len(rows)}\n")

    # risk_map_predictions.csv
    path_risk = os.path.join(PROJECT_ROOT, 'reland-backend', 'risk_map_predictions.csv')
    if not os.path.exists(path_risk):
        print(f"⚠️  risk_map_predictions.csv not found at {path_risk}\n")
        return
    print("=" * 60)
    print("CSV: reland-backend/risk_map_predictions.csv (DB seed)")
    print("=" * 60)
    with open(path_risk, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        rows2 = list(reader)
    if not rows2:
        print("  (empty file)\n")
        return
    mcol2 = 'Municipio' if 'Municipio' in rows2[0] else ('municipio' if 'municipio' in rows2[0] else None)
    if mcol2 is None:
        print("  Columns (first 15):", list(rows2[0].keys())[:15])
    else:
        counts2 = Counter(r[mcol2] for r in rows2)
        print("\nRows per municipality:")
        for name in sorted(counts2.keys()):
            print(f"  {name!r}: {counts2[name]} rows")
    print(f"  Total rows in CSV: {len(rows2)}\n")


if __name__ == '__main__':
    db_checks()
    csv_checks()
    print("Done.")
