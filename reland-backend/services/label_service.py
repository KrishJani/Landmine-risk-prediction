"""
Label service for managing user labels
"""
from typing import Optional, Dict, Any
from sqlalchemy import func
from models import db, Location, UserLabel
from exceptions import NotFoundError, ValidationError, DatabaseError
from datetime import datetime


class LabelService:
    """Service for label-related operations"""
    
    @staticmethod
    def get_all() -> list:
        """Get all user labels"""
        try:
            return UserLabel.query.all()
        except Exception as e:
            raise DatabaseError(f"Failed to fetch labels: {str(e)}")
    
    @staticmethod
    def get_by_location_id(location_id: int) -> Optional[UserLabel]:
        """Get label by location ID"""
        return UserLabel.query.filter_by(location_id=location_id).first()
    
    @staticmethod
    def create_or_update(data: Dict[str, Any]) -> UserLabel:
        """
        Create or update a label for a location
        
        Args:
            data: Dictionary containing label data
            
        Returns:
            UserLabel object
        """
        location_id = data.get('location_id')
        lat = data.get('lat')
        lon = data.get('lon')
        label = data.get('label')
        notes = data.get('notes', '')
        
        # Validate label value
        if label not in [0, 1]:
            raise ValidationError("label must be 0 or 1")
        
        # Find or create location
        location = LabelService._find_or_create_location(location_id, lat, lon)
        
        # Find existing label
        existing_label = LabelService.get_by_location_id(location.id)
        
        if existing_label:
            old_label = existing_label.label
            existing_label.label = label
            existing_label.notes = notes
            existing_label.updated_at = datetime.utcnow()
            
            try:
                db.session.commit()
                return existing_label
            except Exception as e:
                db.session.rollback()
                raise DatabaseError(f"Failed to update label: {str(e)}")
        else:
            new_label = UserLabel(
                location_id=location.id,
                label=label,
                notes=notes
            )
            try:
                db.session.add(new_label)
                db.session.commit()
                return new_label
            except Exception as e:
                db.session.rollback()
                raise DatabaseError(f"Failed to create label: {str(e)}")
    
    @staticmethod
    def _find_or_create_location(location_id: Optional[int], lat: Optional[float], lon: Optional[float]) -> Location:
        """Find existing location or create new one"""
        if location_id:
            location = Location.query.get(location_id)
            if not location:
                raise NotFoundError("Location not found")
            return location
        elif lat is not None and lon is not None:
            # Try to find nearby location
            location = Location.query.filter(
                func.abs(Location.lat - float(lat)) < 0.0001,
                func.abs(Location.lon - float(lon)) < 0.0001
            ).first()
            
            if not location:
                # Try broader search
                nearby = Location.query.filter(
                    func.abs(Location.lat - float(lat)) < 0.01,
                    func.abs(Location.lon - float(lon)) < 0.01
                ).first()
                
                # Try to find municipality from shapefile if available
                municipio_name = None
                if nearby:
                    municipio_name = nearby.municipio
                else:
                    municipio_name = LabelService._find_municipio_from_coords(float(lat), float(lon))
                
                location = Location(
                    lat=float(lat),
                    lon=float(lon),
                    municipio=municipio_name if municipio_name else 'Unknown',
                    risk_score=None,
                    risk_level='Unknown'
                )
                db.session.add(location)
                db.session.flush()
            
            return location
        else:
            raise ValidationError("Either location_id or (lat, lon) coordinates are required")
    
    @staticmethod
    def _find_municipio_from_coords(lat: float, lon: float) -> Optional[str]:
        """Find municipio name from coordinates using shapefile"""
        try:
            from municipality_borders import load_municipality_borders
            import geopandas as gpd
            from shapely.geometry import Point
            
            gdf = load_municipality_borders()
            point = Point(float(lon), float(lat))
            containing = gdf[gdf.geometry.contains(point)]
            
            if len(containing) > 0:
                return containing.iloc[0]['MPIO_CNMBR']
        except Exception:
            pass
        return None
    
    @staticmethod
    def delete(location_id: int) -> None:
        """Delete a label for a location"""
        label = LabelService.get_by_location_id(location_id)
        if not label:
            raise NotFoundError("Label not found")
        
        try:
            db.session.delete(label)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise DatabaseError(f"Failed to delete label: {str(e)}")
