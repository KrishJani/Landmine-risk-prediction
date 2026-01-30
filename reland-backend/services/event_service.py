"""
Event service for managing confirmed events
"""
from typing import List, Optional, Dict, Any
from models import db, ConfirmedEvent
from exceptions import NotFoundError, ValidationError, DatabaseError
from datetime import datetime


class EventService:
    """Service for confirmed event operations"""
    
    @staticmethod
    def get_all(municipio: Optional[str] = None) -> List[ConfirmedEvent]:
        """Get all confirmed events, optionally filtered by municipio"""
        try:
            query = ConfirmedEvent.query
            
            if municipio:
                query = query.filter_by(municipio=municipio)
            
            return query.order_by(
                ConfirmedEvent.event_date.desc() if ConfirmedEvent.event_date 
                else ConfirmedEvent.created_at.desc()
            ).all()
        except Exception as e:
            raise DatabaseError(f"Failed to fetch events: {str(e)}")
    
    @staticmethod
    def get_by_id(event_id: int) -> ConfirmedEvent:
        """Get event by ID"""
        event = ConfirmedEvent.query.get(event_id)
        if not event:
            raise NotFoundError(f"Event with id {event_id} not found")
        return event
    
    @staticmethod
    def create(data: Dict[str, Any]) -> ConfirmedEvent:
        """Create a new confirmed event"""
        lat = data.get('lat')
        lon = data.get('lon')
        municipio = data.get('municipio')
        
        if not all([lat, lon, municipio]):
            raise ValidationError("lat, lon, and municipio are required")
        
        event = ConfirmedEvent(
            lat=float(lat),
            lon=float(lon),
            municipio=municipio,
            departamento=data.get('departamento'),
            event_date=datetime.fromisoformat(data['event_date']) if data.get('event_date') else None,
            description=data.get('description', ''),
            source=data.get('source', 'manual'),
            location_id=data.get('location_id')
        )
        
        try:
            db.session.add(event)
            db.session.commit()
            return event
        except Exception as e:
            db.session.rollback()
            raise DatabaseError(f"Failed to create event: {str(e)}")
    
    @staticmethod
    def update(event_id: int, data: Dict[str, Any]) -> ConfirmedEvent:
        """Update a confirmed event"""
        event = EventService.get_by_id(event_id)
        
        updatable_fields = [
            'lat', 'lon', 'municipio', 'departamento', 
            'event_date', 'description', 'source'
        ]
        
        for field in updatable_fields:
            if field in data:
                value = data[field]
                if field == 'lat' or field == 'lon':
                    value = float(value) if value is not None else None
                elif field == 'event_date':
                    value = datetime.fromisoformat(value) if value else None
                setattr(event, field, value)
        
        event.updated_at = datetime.utcnow()
        
        try:
            db.session.commit()
            return event
        except Exception as e:
            db.session.rollback()
            raise DatabaseError(f"Failed to update event: {str(e)}")
    
    @staticmethod
    def delete(event_id: int) -> None:
        """Delete a confirmed event"""
        event = EventService.get_by_id(event_id)
        
        try:
            db.session.delete(event)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise DatabaseError(f"Failed to delete event: {str(e)}")
