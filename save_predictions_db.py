"""
Utility functions to save predictions to database
"""
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
import os

def save_predictions_to_db(predictions_df, db_url=None):
    """
    Save predictions to database by matching coordinates.
    
    Args:
        predictions_df: DataFrame with columns ['LONGITUD_X', 'LATITUD_Y', 'predicted_proba']
        db_url: Database connection string. If None, reads from DATABASE_URL env var.
    
    Returns:
        int: Number of locations updated
    """
    if db_url is None:
        db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    engine = create_engine(db_url)
    
    # Use raw SQL for bulk update (much faster than ORM)
    updated_count = 0
    
    print(f"Saving {len(predictions_df)} predictions to database...")
    
    # Batch update using SQL UPDATE with CASE statements
    # This is much faster than row-by-row updates
    batch_size = 1000
    for i in range(0, len(predictions_df), batch_size):
        batch = predictions_df.iloc[i:i+batch_size]
        
        # Build CASE statements for bulk update
        lon_cases = []
        lat_cases = []
        proba_cases = []
        
        for _, row in batch.iterrows():
            lon = float(row['LONGITUD_X'])
            lat = float(row['LATITUD_Y'])
            proba = float(row['predicted_proba'])
            
            # Use coordinate matching with small tolerance
            lon_cases.append(f"WHEN ABS(lon - {lon}) < 0.0001 AND ABS(lat - {lat}) < 0.0001 THEN {lon}")
            lat_cases.append(f"WHEN ABS(lon - {lon}) < 0.0001 AND ABS(lat - {lat}) < 0.0001 THEN {lat}")
            
            # Calculate risk_level
            if proba < 0.33:
                risk_level = "'Low'"
            elif proba < 0.67:
                risk_level = "'Medium'"
            else:
                risk_level = "'High'"
            
            proba_cases.append(f"WHEN ABS(lon - {lon}) < 0.0001 AND ABS(lat - {lat}) < 0.0001 THEN {proba}")
        
        # For simplicity, use individual updates per batch (still faster than row-by-row)
        with engine.connect() as conn:
            for _, row in batch.iterrows():
                lon = float(row['LONGITUD_X'])
                lat = float(row['LATITUD_Y'])
                proba = float(row['predicted_proba'])
                
                # Calculate risk_level
                if proba < 0.33:
                    risk_level = 'Low'
                elif proba < 0.67:
                    risk_level = 'Medium'
                else:
                    risk_level = 'High'
                
                # Update using coordinate matching (using SQLAlchemy text for raw SQL)
                from sqlalchemy import text
                result = conn.execute(
                    text("""
                        UPDATE locations 
                        SET risk_score = :proba,
                            risk_level = :risk_level,
                            updated_at = NOW()
                        WHERE ABS(lon - :lon) < 0.0001 
                          AND ABS(lat - :lat) < 0.0001
                    """),
                    {"proba": proba, "risk_level": risk_level, "lon": lon, "lat": lat}
                )
                updated_count += result.rowcount
                conn.commit()
        
        if (i + batch_size) % 5000 == 0:
            print(f"  Updated {updated_count} locations...")
    
    print(f"✓ Successfully updated {updated_count} locations in database")
    return updated_count


def save_predictions_to_db_orm(predictions_df, db_session, Location):
    """
    Save predictions using SQLAlchemy ORM (alternative method).
    Slower but more maintainable.
    
    Args:
        predictions_df: DataFrame with columns ['LONGITUD_X', 'LATITUD_Y', 'predicted_proba']
        db_session: SQLAlchemy session
        Location: Location model class
    
    Returns:
        int: Number of locations updated
    """
    updated_count = 0
    tolerance = 0.0001  # ~11 meters
    
    print(f"Saving {len(predictions_df)} predictions to database...")
    
    for _, row in predictions_df.iterrows():
        lon = float(row['LONGITUD_X'])
        lat = float(row['LATITUD_Y'])
        proba = float(row['predicted_proba'])
        
        # Find location by coordinates
        location = db_session.query(Location).filter(
            func.abs(Location.lon - lon) < tolerance,
            func.abs(Location.lat - lat) < tolerance
        ).first()
        
        if location:
            location.risk_score = proba
            # Calculate risk_level
            if proba < 0.33:
                location.risk_level = 'Low'
            elif proba < 0.67:
                location.risk_level = 'Medium'
            else:
                location.risk_level = 'High'
            updated_count += 1
    
    db_session.commit()
    print(f"✓ Successfully updated {updated_count} locations in database")
    return updated_count


def save_predictions_to_db_by_locations(db_locations, predictions_array, db_session, Location, use_quantiles=True):
    """
    Assign one prediction per DB location (by index), then set risk_level using
    quantile-based binning so stored levels match map display.
    Use when predictions_array is already one-to-one with db_locations (e.g. predicted per DB location).

    Args:
        db_locations: list of Location ORM objects (same order as predictions_array)
        predictions_array: 1D array of predicted probability, length = len(db_locations)
        db_session: SQLAlchemy session
        Location: Location model class (unused, for API consistency)
        use_quantiles: if True, set risk_level by quantiles (Low/Medium/High = bottom/mid/top third)

    Returns:
        int: Number of locations updated
    """
    n = len(db_locations)
    if n != len(predictions_array):
        raise ValueError(
            f"Length mismatch: {n} locations vs {len(predictions_array)} predictions"
        )
    predictions_array = np.asarray(predictions_array, dtype=np.float64)
    valid = np.isfinite(predictions_array)
    if use_quantiles and np.sum(valid) >= 3:
        scores_sorted = np.sort(predictions_array[valid])
        nn = len(scores_sorted)
        q_low = scores_sorted[nn // 3]
        q_high = scores_sorted[2 * nn // 3]
    else:
        q_low, q_high = 1.0 / 3.0, 2.0 / 3.0

    for i, loc in enumerate(db_locations):
        proba = float(predictions_array[i])
        loc.risk_score = proba if np.isfinite(proba) else None
        if loc.risk_score is None:
            loc.risk_level = 'Low'
        elif use_quantiles and np.sum(valid) >= 3:
            if proba <= q_low:
                loc.risk_level = 'Low'
            elif proba <= q_high:
                loc.risk_level = 'Medium'
            else:
                loc.risk_level = 'High'
        else:
            if proba < 0.33:
                loc.risk_level = 'Low'
            elif proba < 0.67:
                loc.risk_level = 'Medium'
            else:
                loc.risk_level = 'High'
    db_session.commit()
    print(f"✓ Successfully updated {n} locations in database (by location, quantile-based risk_level)")
    return n

