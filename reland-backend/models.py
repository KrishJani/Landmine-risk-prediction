"""
Database models for RELand application
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Location(db.Model):
    """
    Stores risk prediction locations from risk_map_predictions.csv
    """
    __tablename__ = 'locations'
    
    id = db.Column(db.Integer, primary_key=True)
    lat = db.Column(db.Float, nullable=False, index=True)
    lon = db.Column(db.Float, nullable=False, index=True)
    municipio = db.Column(db.String(100), nullable=False, index=True)
    
    # Risk prediction data
    risk_score = db.Column(db.Float)
    risk_score_lr = db.Column(db.Float)
    risk_level = db.Column(db.String(20))  # Low, Medium, High
    
    # Feature data (storing key features)
    elevation = db.Column(db.Float)
    rainfall = db.Column(db.Float)
    temperature = db.Column(db.Float)
    population_2012 = db.Column(db.Float)
    hist_mines = db.Column(db.Float)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user_labels = db.relationship('UserLabel', backref='location', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'lat': self.lat,
            'lon': self.lon,
            'municipio': self.municipio,
            'risk_score': self.risk_score,
            'risk_score_lr': self.risk_score_lr,
            'risk_level': self.risk_level,
            'elevation': self.elevation,
            'rainfall': self.rainfall,
            'temperature': self.temperature,
            'population_2012': self.population_2012,
            'hist_mines': self.hist_mines
        }


class UserLabel(db.Model):
    """
    Stores user-assigned labels (0 = mine-free, 1 = confirmed mine)
    """
    __tablename__ = 'user_labels'
    
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)
    label = db.Column(db.Integer, nullable=False)  # 0 or 1
    notes = db.Column(db.Text)  # Optional user notes
    user_id = db.Column(db.String(50), default='default')  # For future multi-user support
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'location_id': self.location_id,
            'label': self.label,
            'notes': self.notes,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'location': self.location.to_dict() if self.location else None
        }


class ConfirmedEvent(db.Model):
    """
    Stores confirmed mine events (from user labels or EO_events)
    """
    __tablename__ = 'confirmed_events'
    
    id = db.Column(db.Integer, primary_key=True)
    lat = db.Column(db.Float, nullable=False, index=True)
    lon = db.Column(db.Float, nullable=False, index=True)
    municipio = db.Column(db.String(100), nullable=False, index=True)
    departamento = db.Column(db.String(100))
    
    # Event details
    event_date = db.Column(db.DateTime)  # Date of the event
    description = db.Column(db.Text)  # Optional description
    source = db.Column(db.String(50), default='user_label')  # 'user_label', 'EO_events', 'manual'
    
    # Reference to original data
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    eo_event_id = db.Column(db.String(50))  # If imported from EO_events
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'lat': self.lat,
            'lon': self.lon,
            'municipio': self.municipio,
            'departamento': self.departamento,
            'event_date': self.event_date.isoformat() if self.event_date else None,
            'description': self.description,
            'source': self.source,
            'location_id': self.location_id,
            'eo_event_id': self.eo_event_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

