"""
Location service for managing location data
"""
from typing import List, Optional, Dict, Any
from sqlalchemy import text, inspect
from models import db, Location
from exceptions import NotFoundError, DatabaseError
from datetime import datetime


class LocationService:
    """Service for location-related operations"""
    
    @staticmethod
    def get_all() -> List[Location]:
        """Get all locations from database"""
        try:
            return Location.query.all()
        except Exception as e:
            raise DatabaseError(f"Failed to fetch locations: {str(e)}")
    
    @staticmethod
    def get_by_id(location_id: int) -> Location:
        """Get location by ID"""
        location = Location.query.get(location_id)
        if not location:
            raise NotFoundError(f"Location with id {location_id} not found")
        return location
    
    @staticmethod
    def get_by_municipios(municipios: List[str]) -> List[Location]:
        """Get locations by municipio names"""
        try:
            # Handle case where dist_old_mine column doesn't exist yet
            try:
                locations = Location.query.filter(Location.municipio.in_(municipios)).all()
            except Exception as db_error:
                # If dist_old_mine column doesn't exist, use raw SQL
                if 'dist_old_mine' in str(db_error) or 'UndefinedColumn' in str(db_error):
                    db.session.rollback()
                    query = text("""
                        SELECT id, lat, lon, municipio, risk_score, risk_score_lr, risk_level,
                               elevation, rainfall, temperature, population_2012, hist_mines,
                               created_at, updated_at
                        FROM locations
                        WHERE municipio = ANY(:municipios)
                    """)
                    result = db.session.execute(query, {'municipios': municipios})
                    locations = LocationService._convert_rows_to_locations(result)
                else:
                    db.session.rollback()
                    raise
            return locations
        except Exception as e:
            raise DatabaseError(f"Failed to fetch locations by municipios: {str(e)}")
    
    @staticmethod
    def _convert_rows_to_locations(result) -> List[Location]:
        """Convert raw SQL rows to Location objects"""
        locations = []
        for row in result:
            loc = Location()
            loc.id = row.id
            loc.lat = row.lat
            loc.lon = row.lon
            loc.municipio = row.municipio
            loc.risk_score = row.risk_score
            loc.risk_score_lr = row.risk_score_lr
            loc.risk_level = row.risk_level
            loc.elevation = row.elevation
            loc.rainfall = row.rainfall
            loc.temperature = row.temperature
            loc.population_2012 = row.population_2012
            loc.hist_mines = row.hist_mines
            loc.created_at = row.created_at
            loc.updated_at = row.updated_at
            loc.dist_old_mine = None  # Set to None since column doesn't exist
            locations.append(loc)
        return locations
    
    @staticmethod
    def update(location_id: int, data: Dict[str, Any]) -> Location:
        """Update a location"""
        location = LocationService.get_by_id(location_id)
        
        # Update fields
        updatable_fields = [
            'risk_score', 'risk_score_lr', 'risk_level', 'municipio',
            'elevation', 'rainfall', 'temperature', 'population_2012', 'hist_mines'
        ]
        
        for field in updatable_fields:
            if field in data:
                value = data[field]
                if value is not None:
                    # Convert to float for numeric fields
                    if field in ['risk_score', 'risk_score_lr', 'elevation', 'rainfall', 
                                'temperature', 'population_2012', 'hist_mines']:
                        value = float(value)
                setattr(location, field, value)
        
        location.updated_at = datetime.utcnow()
        
        try:
            db.session.commit()
            return location
        except Exception as e:
            db.session.rollback()
            raise DatabaseError(f"Failed to update location: {str(e)}")
    
    @staticmethod
    def bulk_update(locations_data: List[Dict[str, Any]]) -> int:
        """Bulk update locations"""
        updated_count = 0
        
        try:
            for loc_data in locations_data:
                location_id = loc_data.get('id')
                if not location_id:
                    continue
                
                location = Location.query.get(location_id)
                if not location:
                    continue
                
                updatable_fields = ['risk_score', 'risk_score_lr', 'risk_level', 'municipio']
                for field in updatable_fields:
                    if field in loc_data:
                        value = loc_data[field]
                        if value is not None and field in ['risk_score', 'risk_score_lr']:
                            value = float(value)
                        setattr(location, field, value)
                
                location.updated_at = datetime.utcnow()
                updated_count += 1
            
            db.session.commit()
            return updated_count
        except Exception as e:
            db.session.rollback()
            raise DatabaseError(f"Failed to bulk update locations: {str(e)}")
    
    @staticmethod
    def get_distinct_municipios() -> List[str]:
        """Get distinct municipio names"""
        try:
            result = db.session.execute(
                db.text("SELECT DISTINCT municipio FROM locations WHERE municipio IS NOT NULL AND municipio != 'Unknown' ORDER BY municipio")
            )
            return [row[0] for row in result if row[0]]
        except Exception as e:
            raise DatabaseError(f"Failed to fetch distinct municipios: {str(e)}")
    
    @staticmethod
    def ensure_dist_old_mine_column() -> bool:
        """Ensure dist_old_mine column exists in database"""
        try:
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('locations')]
            
            if 'dist_old_mine' not in columns:
                db.session.execute(text("ALTER TABLE locations ADD COLUMN dist_old_mine FLOAT"))
                db.session.commit()
                return True
            return False
        except Exception as e:
            db.session.rollback()
            raise DatabaseError(f"Failed to ensure dist_old_mine column: {str(e)}")
    
    @staticmethod
    def update_distances(location_ids: List[int], distances: List[float]) -> int:
        """Update dist_old_mine for multiple locations"""
        try:
            update_query = text("""
                UPDATE locations 
                SET dist_old_mine = :distance 
                WHERE id = :location_id
            """)
            
            updated_count = 0
            for location_id, distance in zip(location_ids, distances):
                db.session.execute(
                    update_query,
                    {'distance': float(distance), 'location_id': location_id}
                )
                updated_count += 1
            
            db.session.commit()
            return updated_count
        except Exception as e:
            db.session.rollback()
            raise DatabaseError(f"Failed to update distances: {str(e)}")
