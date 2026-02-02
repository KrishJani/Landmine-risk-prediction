import pandas as pd
import numpy as np

from sklearn.preprocessing import StandardScaler
from sklearn.impute import KNNImputer

import torch
from torch.utils.data import Dataset

from typing import *
import os
from sqlalchemy import create_engine, func

class EventDB(Dataset):
    """
    Hybrid dataset class that loads static features from CSV and dynamic features from database.
    This provides the best performance: fast CSV reading + dynamic database updates.
    """
    def __init__(self, 
                 train_municipios : List[str], val_municipio : str, 
                 subset : str, split : str,
                 db_url : str = None):
        """
        Landmine dataset class with database integration.

        Args:
            train_municipios (List[str]) : training municipalities. If split != 'train', load for normalization.
            val_munipio (str) : the validation municipality.
            subset (str): full | geo | single
            split (str) : train | val
            db_url (str): Database connection string. If None, reads from DATABASE_URL env var.
        """ 
        self.split = split
        self.val_municipio = val_municipio
        
        # Get database URL
        if db_url is None:
            # Match backend behavior:
            # - Production: DATABASE_URL (RDS) is required
            # - Local: LOCAL_DATABASE_URL is required (no fallback to production DB)
            env = os.getenv('FLASK_ENV', os.getenv('ENVIRONMENT', 'local')).lower()
            if env in ['production', 'prod']:
                db_url = os.getenv('DATABASE_URL')
                if not db_url:
                    raise ValueError(
                        "DATABASE_URL environment variable is required in production. "
                        "Please set it in your deployment platform (AWS App Runner, Docker, etc.)."
                    )
            else:
                # Local mode: ONLY use LOCAL_DATABASE_URL (never touch production DB)
                db_url = os.getenv('LOCAL_DATABASE_URL')
                if not db_url:
                    raise ValueError(
                        "LOCAL_DATABASE_URL environment variable is required for local development. "
                        "Set it in your .env file to avoid accidentally connecting to production database."
                    )
        if not db_url:
            raise ValueError("Database URL not set.")
        
        # Load static features from CSV (fast, one-time read)
        # Always use absolute paths to avoid issues with different working directories
        # dataset_db.py is in project root, so processed_dataset should be in the same directory
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Try multiple possible locations (all as absolute paths)
        possible_paths = [
            os.path.join(current_file_dir, 'processed_dataset', 'resolution_0.5.csv'),  # Same directory as dataset_db.py
            os.path.join(os.path.dirname(current_file_dir), 'processed_dataset', 'resolution_0.5.csv'),  # Parent directory
            os.path.abspath(os.path.join(os.getcwd(), 'processed_dataset', 'resolution_0.5.csv')),  # Absolute from CWD
        ]
        
        data_path = None
        for path in possible_paths:
            # Always convert to absolute path before checking
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                data_path = abs_path
                break
        
        if not data_path:
            raise FileNotFoundError(
                f"Dataset file not found: resolution_0.5.csv\n"
                f"Tried locations (all as absolute paths):\n" + 
                "\n".join([f"  - {os.path.abspath(p)}" for p in possible_paths]) +
                f"\n\nCurrent working directory: {os.getcwd()}\n"
                f"dataset_db.py location: {current_file_dir}\n"
                f"Please ensure processed_dataset/resolution_0.5.csv exists in the project root."
            )
        
        print(f"Loading static features from CSV: {data_path}")
        data = pd.read_csv(data_path)
        print(f"  Loaded {len(data)} rows from CSV")
        
        # Load dynamic features from database (only dist_old_mine)
        print("Loading dynamic features from database...")
        engine = create_engine(db_url)
        db_query = """
            SELECT 
                l.lon as LONGITUD_X,
                l.lat as LATITUD_Y,
                l.dist_old_mine,
                COALESCE(ul.label, 0) as mines_outcome_db
            FROM locations l
            LEFT JOIN user_labels ul ON l.id = ul.location_id AND ul.label = 1
        """
        db_data = pd.read_sql(db_query, engine)
        print(f"  Loaded {len(db_data)} rows from database")
        print(f"  Database columns: {list(db_data.columns)}")
        
        # Handle case sensitivity - PostgreSQL may return lowercase column names
        # Normalize column names to match expected format (uppercase)
        column_mapping = {}
        for col in db_data.columns:
            col_upper = col.upper()
            # Map to expected uppercase names
            if col_upper == 'LONGITUD_X' or col == 'longitud_x' or col == 'lon':
                column_mapping[col] = 'LONGITUD_X'
            elif col_upper == 'LATITUD_Y' or col == 'latitud_y' or col == 'lat':
                column_mapping[col] = 'LATITUD_Y'
        
        if column_mapping:
            db_data = db_data.rename(columns=column_mapping)
            print(f"  Renamed columns: {column_mapping}")
        
        # Verify required columns exist (check both original and mapped names)
        required_cols = ['LONGITUD_X', 'LATITUD_Y']
        missing_cols = [col for col in required_cols if col not in db_data.columns]
        if missing_cols:
            # Try to find alternative column names
            available_cols_upper = [c.upper() for c in db_data.columns]
            error_msg = (
                f"Missing required columns in database query result: {missing_cols}\n"
                f"Available columns: {list(db_data.columns)}\n"
                f"Available columns (uppercase): {available_cols_upper}\n"
            )
            # Check if columns exist with different case
            if 'LONGITUD_X' in missing_cols:
                if 'longitud_x' in db_data.columns:
                    db_data = db_data.rename(columns={'longitud_x': 'LONGITUD_X'})
                    missing_cols.remove('LONGITUD_X')
                elif 'lon' in db_data.columns:
                    db_data = db_data.rename(columns={'lon': 'LONGITUD_X'})
                    missing_cols.remove('LONGITUD_X')
            if 'LATITUD_Y' in missing_cols:
                if 'latitud_y' in db_data.columns:
                    db_data = db_data.rename(columns={'latitud_y': 'LATITUD_Y'})
                    missing_cols.remove('LATITUD_Y')
                elif 'lat' in db_data.columns:
                    db_data = db_data.rename(columns={'lat': 'LATITUD_Y'})
                    missing_cols.remove('LATITUD_Y')
            
            if missing_cols:
                raise ValueError(error_msg + "Please check the SQL query and database schema.")
        
        # Merge database data with CSV data on coordinates
        # Use a tolerance for coordinate matching (0.0001 degrees ≈ 11 meters)
        print("Merging CSV and database data...")
        data['merge_key'] = data.apply(
            lambda row: f"{row['LONGITUD_X']:.6f}_{row['LATITUD_Y']:.6f}", axis=1
        )
        db_data['merge_key'] = db_data.apply(
            lambda row: f"{row['LONGITUD_X']:.6f}_{row['LATITUD_Y']:.6f}", axis=1
        )
        
        # Merge on coordinates
        merged = data.merge(
            db_data[['merge_key', 'dist_old_mine', 'mines_outcome_db']],
            on='merge_key',
            how='left',
            suffixes=('_csv', '_db')
        )
        
        # Update dist_old_mine from database if available, otherwise keep CSV value
        if 'dist_old_mine_db' in merged.columns:
            # Use database value if available, otherwise use CSV value
            if 'dist_old_mine_csv' in merged.columns:
                merged['dist_old_mine'] = merged['dist_old_mine_db'].fillna(merged['dist_old_mine_csv'])
                merged = merged.drop(columns=['dist_old_mine_csv'], errors='ignore')
            else:
                # CSV doesn't have dist_old_mine, use DB value
                merged['dist_old_mine'] = merged['dist_old_mine_db']
            # Drop the DB column
            merged = merged.drop(columns=['dist_old_mine_db'], errors='ignore')
        elif 'dist_old_mine_csv' in merged.columns:
            # No DB column, keep CSV value
            merged['dist_old_mine'] = merged['dist_old_mine_csv']
            merged = merged.drop(columns=['dist_old_mine_csv'], errors='ignore')
        # If neither exists, dist_old_mine column will be missing (will be handled by feature selection)
        
        # Use database labels if available, otherwise use CSV labels
        if 'mines_outcome_db' in merged.columns:
            # Only update if database has a label (1), otherwise keep CSV value
            merged['mines_outcome'] = merged.apply(
                lambda row: row['mines_outcome_db'] if pd.notna(row['mines_outcome_db']) and row['mines_outcome_db'] == 1 
                           else row['mines_outcome'], axis=1
            )
            merged = merged.drop(columns=['mines_outcome_db'])
        
        data = merged.drop(columns=['merge_key'], errors='ignore')
        
        print(f"  Merged data: {len(data)} rows")
        
        all_locations = data[['LONGITUD_X','LATITUD_Y']].to_numpy()
        all_hist_mine = data['0.5km_hist_mines'].to_numpy()
        
        if subset == 'full':
            self.numeric_cols = ['airports_dist','seaport_dist', 'settlement_dist', 'finance_dist', 'edu_dist',
                                'buildings_dist', 'waterways_dist', 'rwi', 'elevation',
                                'roads_dist', 'No. Víctimas por Declaración',
                                'retro_pobl_tot', 'indrural', 'dist_old_mine',
                                'areaoficialkm2', 'altura', 'discapital', 'pib_percapita_cons', 'hist_mines',
                                'rainfall', 'temperature', 'dist_roads_t1', 'dist_roads_t2', 'dist_roads_t3',
                                'population_2012', 'coca_dist', 'soil_texture15_trans1', 'soil_texture15_trans2',
                                'nighttime_lights_2012', 'dist_pipeline','dist_powerline','dist_telecom','dist_mining',
                                'forest_gain','forest_loss',
                                '0.5km_hist_mines','2.0km_hist_mines','8.0km_hist_mines','16.0km_hist_mines','32.0km_hist_mines',
                                'animal_inc','animal_dec',
                                'LONGITUD_X', 'LATITUD_Y'] 

            self.binary_cols = ['binary_hist_mine',
                                'land_use_Agroforestal', 'land_use_Agrícola',
                                'land_use_Conservación de Suelos', 'land_use_Cuerpo de agua',
                                'land_use_Forestal', 'land_use_Ganadera', 'land_use_Zonas urbanas',
                                'weather_Cuerpo de agua', 'weather_Cálido húmedo',
                                'weather_Cálido húmedo a muy húmedo', 'weather_Cálido seco a húmedo',
                                'weather_Frío húmedo a muy húmedo',
                                'weather_Frío húmedo y frío muy húmedo', 'weather_Frío muy húmedo',
                                'weather_Muy frío y muy húmedo', 'weather_Templado húmedo a muy húmedo',
                                'weather_Zona urbana', 'relief_Cuerpo de agua', 'relief_Espinazos',
                                'relief_Filas y vigas', 'relief_Glacís coluvial y coluvios de remoción',
                                'relief_Glacís y coluvios de remoción', 'relief_Lomas y colinas',
                                'relief_Terrazas y abanicos terrazas', 'relief_Vallecitos',
                                'relief_Vallecitos coluvio-aluviales', 'relief_Zona urbana']
        elif subset == 'geo':
            self.numeric_cols = ['airports_dist','seaport_dist', 'settlement_dist', 'finance_dist', 'edu_dist',
                                'buildings_dist', 'waterways_dist', 'rwi', 'elevation',
                                'roads_dist', 'No. Víctimas por Declaración',
                                'retro_pobl_tot', 'indrural', 
                                'areaoficialkm2', 'altura', 'discapital', 'pib_percapita_cons', 'hist_mines',
                                'rainfall', 'temperature', 'dist_roads_t1', 'dist_roads_t2', 'dist_roads_t3',
                                'population_2012', 'coca_dist', 'soil_texture15_trans1', 'soil_texture15_trans2',
                                'nighttime_lights_2012', 'dist_pipeline','dist_powerline','dist_telecom','dist_mining',
                                'forest_gain','forest_loss',
                                'animal_inc','animal_dec',
                                'LONGITUD_X', 'LATITUD_Y'] 

            self.binary_cols = ['land_use_Agroforestal', 'land_use_Agrícola',
                                'land_use_Conservación de Suelos', 'land_use_Cuerpo de agua',
                                'land_use_Forestal', 'land_use_Ganadera', 'land_use_Zonas urbanas',
                                'weather_Cuerpo de agua', 'weather_Cálido húmedo',
                                'weather_Cálido húmedo a muy húmedo', 'weather_Cálido seco a húmedo',
                                'weather_Frío húmedo a muy húmedo',
                                'weather_Frío húmedo y frío muy húmedo', 'weather_Frío muy húmedo',
                                'weather_Muy frío y muy húmedo', 'weather_Templado húmedo a muy húmedo',
                                'weather_Zona urbana', 'relief_Cuerpo de agua', 'relief_Espinazos',
                                'relief_Filas y vigas', 'relief_Glacís coluvial y coluvios de remoción',
                                'relief_Glacís y coluvios de remoción', 'relief_Lomas y colinas',
                                'relief_Terrazas y abanicos terrazas', 'relief_Vallecitos',
                                'relief_Vallecitos coluvio-aluviales', 'relief_Zona urbana']
        
        elif subset == 'single':
            self.numeric_cols = ['dist_old_mine']
            self.binary_cols = []
        
        self.features = self.numeric_cols + self.binary_cols
        
        tabX = pd.get_dummies(columns=['land_use', 'weather', 'relief'], data = data)[self.features]
        if val_municipio == 'RANDOM' or val_municipio == 'PUERTO LIBERTADOR' or val_municipio == 'MURINDÓ': # train_val split + test
            train_tabX_combined = tabX.loc[list(data[data['Municipio'].isin(train_municipios)].index),self.features]
            np.random.RandomState(737)
            train_idx = pd.Index(np.random.choice(train_tabX_combined.index, int(len(train_tabX_combined)*0.7), replace=False))
            train_tabX = train_tabX_combined.loc[train_idx]
            if val_municipio == 'RANDOM':
                val_tabX = train_tabX_combined.loc[~train_tabX_combined.index.isin(train_idx)]
            elif val_municipio == 'PUERTO LIBERTADOR' or val_municipio == 'MURINDÓ':
                val_tabX = tabX.loc[list(data[data['Municipio'] == val_municipio].index),self.features]
        else:
            train_tabX = tabX.loc[list(data[data['Municipio'].isin(train_municipios)].index),self.features]
            val_municipio_filtered = data[data['Municipio'] == val_municipio]
            if len(val_municipio_filtered) == 0:
                # If val_municipio not found, use all data for prediction (common for blockCV or when predicting on all locations)
                print(f"  ⚠️  Warning: Municipio '{val_municipio}' not found in data. Using all locations for prediction.")
                print(f"  Available municipios: {sorted(data['Municipio'].unique())}")
                val_tabX = tabX.loc[:, self.features]  # Use all data
            else:
                val_tabX = tabX.loc[list(val_municipio_filtered.index),self.features]
        
        imputer = KNNImputer(n_neighbors = 4, weights = 'distance')
        train_imputer = imputer.fit(train_tabX)
        if len(np.where(np.isnan(train_tabX).any(axis=0))[0]) != 0:
            idx = np.where(np.isnan(train_tabX).any(axis=0))[0][0]  # find the nan column
            train_tabX.iloc[:,idx] = train_imputer.transform(train_tabX)[:,idx]
            # Only transform val_tabX if it has data
            if len(val_tabX) > 0:
                val_tabX.iloc[:,idx] = train_imputer.transform(val_tabX)[:,idx]
            else:
                print(f"  ⚠️  Warning: val_tabX is empty for municipio '{val_municipio}'. Skipping imputation.")
                print(f"  Available municipios in data: {sorted(data['Municipio'].unique())}")
        
        scaler = StandardScaler()
        train_scaler = scaler.fit(train_tabX[self.numeric_cols])
        train_tabX[self.numeric_cols] = train_scaler.transform(train_tabX[self.numeric_cols])
        # Only transform val_tabX if it has data
        if len(val_tabX) > 0:
            val_tabX[self.numeric_cols] = train_scaler.transform(val_tabX[self.numeric_cols])
        else:
            print(f"  ⚠️  Warning: val_tabX is empty. Cannot apply scaling.")
    
        # Helper function to convert DataFrame to numeric numpy array
        def to_numeric_array(df):
            """Convert DataFrame to float32 numpy array, handling object dtype."""
            if len(df) == 0:
                return np.array([], dtype=np.float32).reshape(0, len(df.columns) if len(df.columns) > 0 else 0)
            # Convert to numpy and ensure float32
            arr = df.values
            # If object dtype, convert to float explicitly
            if arr.dtype == np.object_:
                arr = arr.astype(np.float64)
            # Convert to float32 for efficiency
            return arr.astype(np.float32)
        
        if self.split == 'val':
            if val_municipio == 'RANDOM':
                # all train - train_idx
                val_idx = train_tabX_combined.index[~train_tabX_combined.index.isin(train_idx)]
                self.locations = all_locations[list(val_idx)]
                self.y = data.loc[val_idx,'mines_outcome'].to_numpy().astype(np.float32)
                self.tabX = to_numeric_array(val_tabX)
                self.hist_mine = all_hist_mine[list(val_idx)].astype(np.float32)
            else:
                val_municipio_filtered = data[data['Municipio'] == val_municipio]
                if len(val_municipio_filtered) == 0:
                    # If municipio not found, use all locations for prediction
                    print(f"  Using all locations for prediction (municipio '{val_municipio}' not found)")
                    self.locations = all_locations
                    self.y = data['mines_outcome'].to_numpy().astype(np.float32)
                    self.tabX = to_numeric_array(val_tabX)
                    self.hist_mine = all_hist_mine.astype(np.float32)
                else:
                    self.locations = all_locations[list(val_municipio_filtered.index)]
                    self.y = (data.loc[val_municipio_filtered.index,'mines_outcome']).to_numpy().astype(np.float32)
                    self.tabX = to_numeric_array(val_tabX)
                    self.hist_mine = all_hist_mine[list(val_municipio_filtered.index)].astype(np.float32)
        elif self.split == 'train': 
            if val_municipio == 'RANDOM' or val_municipio == 'PUERTO LIBERTADOR' or val_municipio == 'MURINDÓ':
                self.locations = all_locations[list(train_idx)]
                self.y = data.loc[train_idx,'mines_outcome'].to_numpy().astype(np.float32)
                self.tabX = to_numeric_array(train_tabX)
                self.hist_mine = all_hist_mine[list(train_idx)].astype(np.float32)
            else:
                self.locations = all_locations[list(data[data['Municipio'].isin(train_municipios)].index)]
                self.y = (data.loc[data['Municipio'].isin(train_municipios),'mines_outcome']).to_numpy().astype(np.float32)
                self.tabX = to_numeric_array(train_tabX)
                self.hist_mine = all_hist_mine[list(data[data['Municipio'].isin(train_municipios)].index)].astype(np.float32)
       
        # for ood bench
        self.samples = [(self.tabX[i], self.y[i])for i in range(len(self.y))]

    def __len__(self):
        return len(self.y)
    
    def __getitem__(self,idx):
        lon, lat = self.locations[idx]
        hist_mine = self.hist_mine[idx]
        label = self.y[idx]
        tab_data = self.tabX[idx,:]
        
        # Ensure tab_data is numeric (handle object dtype)
        if tab_data.dtype == np.object_:
            tab_data = tab_data.astype(np.float32)
        elif not np.issubdtype(tab_data.dtype, np.number):
            tab_data = np.array(tab_data, dtype=np.float32)
        
        return  (torch.tensor(tab_data, dtype=torch.float32),\
                torch.tensor(label, dtype=torch.float32), \
                torch.tensor((lon, lat), dtype=torch.float32), \
                torch.tensor(hist_mine, dtype=torch.float32))

