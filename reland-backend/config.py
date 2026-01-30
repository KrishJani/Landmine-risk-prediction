"""
Configuration module for RELand Backend
Handles environment-specific configuration loading
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional


class Config:
    """Base configuration class"""
    
    # Flask configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_timeout': 10,
        'connect_args': {
            'connect_timeout': 10
        }
    }
    
    # Database configuration
    DATABASE_URL: Optional[str] = None
    
    # API configuration
    GOOGLE_GEOCODING_API_KEY: Optional[str] = None
    
    # AWS configuration
    AWS_REGION: str = os.getenv('AWS_REGION', 'us-east-1')
    EC2_LAUNCH_TEMPLATE_NAME: str = os.getenv('EC2_LAUNCH_TEMPLATE_NAME', 'reland-worker-template')
    
    # Application configuration
    PORT: int = int(os.getenv('PORT', 5001))
    DEBUG: bool = False
    
    # Paths configuration
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    BACKEND_ROOT: Path = Path(__file__).parent
    EXPERIMENTS_DIR: Path = PROJECT_ROOT / 'experiments'
    MUNICIPALITY_DATA_DIR: Path = BACKEND_ROOT / 'Muncipality Data'
    SHAPEFILE_PATH: Path = MUNICIPALITY_DATA_DIR / 'Municipios.shp'
    
    def init_app(self, app):
        """Initialize Flask app with configuration"""
        # Use instance variable (set in __init__) not class variable
        app.config['SQLALCHEMY_DATABASE_URI'] = self.DATABASE_URL
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = self.SQLALCHEMY_TRACK_MODIFICATIONS
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = self.SQLALCHEMY_ENGINE_OPTIONS


class LocalConfig(Config):
    """Local development configuration"""
    DEBUG = True
    
    def __init__(self):
        super().__init__()
        # Load .env file for local development (standard practice)
        env_file = self.BACKEND_ROOT / '.env'
        if env_file.exists():
            load_dotenv(env_file, override=False)
        
        # Local development: ONLY use LOCAL_DATABASE_URL (never touch production DATABASE_URL)
        # This ensures localhost never accidentally connects to RDS
        self.DATABASE_URL = os.getenv('LOCAL_DATABASE_URL')
        if not self.DATABASE_URL:
            # Fallback to default localhost connection (not production)
            self.DATABASE_URL = 'postgresql://reland_user:reland_password123@localhost:5432/reland_db'
            import warnings
            warnings.warn(
                "⚠️  LOCAL_DATABASE_URL not set, using default localhost connection. "
                "Set LOCAL_DATABASE_URL in .env for explicit local database configuration.",
                UserWarning
            )
        
        self.GOOGLE_GEOCODING_API_KEY = os.getenv('GOOGLE_GEOCODING_API_KEY')
        
        # Local paths
        self.EXPERIMENTS_DIR = self.PROJECT_ROOT / 'experiments'
        if not self.EXPERIMENTS_DIR.exists():
            self.EXPERIMENTS_DIR = Path(os.getcwd()) / 'experiments'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    
    def __init__(self):
        super().__init__()
        # In production, environment variables are set by the deployment platform
        # (AWS App Runner, Docker, etc.) - do NOT use .env files in production
        # Environment variables take precedence and are set by the platform
        
        self.DATABASE_URL = os.getenv('DATABASE_URL')
        if not self.DATABASE_URL:
            raise ValueError(
                "DATABASE_URL environment variable is required in production. "
                "Please set it in your deployment platform (AWS App Runner, Docker, etc.)."
            )
        
        # Ensure SSL is enabled for RDS connections
        if '.rds.amazonaws.com' in self.DATABASE_URL and 'sslmode' not in self.DATABASE_URL:
            if '?' not in self.DATABASE_URL:
                self.DATABASE_URL += '?sslmode=require'
            else:
                self.DATABASE_URL += '&sslmode=require'
        
        # Update engine options for production (RDS requires SSL)
        if '.rds.amazonaws.com' in self.DATABASE_URL:
            self.SQLALCHEMY_ENGINE_OPTIONS = {
                'pool_pre_ping': True,
                'pool_recycle': 3600,  # Recycle connections after 1 hour
                'pool_timeout': 20,
                'max_overflow': 10,
                'connect_args': {
                    'connect_timeout': 30,
                    'sslmode': 'require'
                }
            }
        
        self.GOOGLE_GEOCODING_API_KEY = os.getenv('GOOGLE_GEOCODING_API_KEY')
        
        # Production paths
        self.EXPERIMENTS_DIR = Path('/app/experiments') if Path('/app').exists() else self.PROJECT_ROOT / 'experiments'


def get_config() -> Config:
    """
    Get configuration based on environment.
    
    Detection logic:
    1. Checks FLASK_ENV environment variable
    2. Falls back to ENVIRONMENT environment variable
    3. Defaults to 'local' if neither is set
    
    Database URL selection:
    - Local: Uses LOCAL_DATABASE_URL (falls back to DATABASE_URL if not set)
    - Production: Uses DATABASE_URL (required, must point to RDS)
    
    This allows the same Docker image to work in both local and production:
    - Local: FLASK_ENV=local → LocalConfig (uses LOCAL_DATABASE_URL from .env)
    - Production: FLASK_ENV=production → ProductionConfig (uses DATABASE_URL from platform)
    
    Returns:
        Config instance appropriate for the current environment
    """
    env = os.getenv('FLASK_ENV', os.getenv('ENVIRONMENT', 'local')).lower()
    
    if env in ['production', 'prod']:
        return ProductionConfig()
    else:
        return LocalConfig()


# Global config instance
config = get_config()
