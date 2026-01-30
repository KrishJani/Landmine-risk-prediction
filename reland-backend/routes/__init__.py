"""
Route handlers for RELand Backend
"""
from flask import Blueprint

# Create main API blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Import route modules to register routes
# Note: Importing these modules registers their routes with the blueprints
from . import (
    health,
    initial_data,
    map_data,
    geocode,
    labels,
    events,
    locations,
    training,
    municipality_borders,
    recalculate
)
