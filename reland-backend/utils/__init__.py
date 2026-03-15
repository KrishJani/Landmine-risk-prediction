"""
Utility modules for RELand Backend
"""
import os
import importlib.util

from .risk_calculator import RiskCalculator
from .distance_calculator import DistanceCalculator
from .model_finder import ModelFinder
from .geocoding import GeocodingService

# Re-export from project root utils.py for model.py, loss.py, reland.py compatibility
# (avoids "cannot import name 'sigmoid' from 'utils'" when backend runs from reland-backend/)
_utils_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_utils_dir))
_root_utils_path = os.path.join(_project_root, "utils.py")
if os.path.exists(_root_utils_path):
    _spec = importlib.util.spec_from_file_location("root_utils", _root_utils_path)
    _root_utils = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_root_utils)
    sigmoid = _root_utils.sigmoid
    mean_reverse_height = _root_utils.mean_reverse_height
    mean_height = _root_utils.mean_height
else:
    sigmoid = mean_reverse_height = mean_height = None

__all__ = [
    'RiskCalculator',
    'DistanceCalculator',
    'ModelFinder',
    'GeocodingService',
    'sigmoid',
    'mean_reverse_height',
    'mean_height',
]
