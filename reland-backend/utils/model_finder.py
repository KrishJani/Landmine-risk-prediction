"""
Model finding utilities
"""
import os
import json
from pathlib import Path
from typing import Optional, Tuple, List
from config import config


class ModelFinder:
    """Handles finding and detecting model files"""

    @staticmethod
    def _get_experiments_dir() -> Optional[Path]:
        experiments_dir = config.EXPERIMENTS_DIR
        cwd_experiments = Path(os.getcwd()) / 'experiments'
        if not experiments_dir.exists() and cwd_experiments.exists():
            experiments_dir = cwd_experiments
        if not experiments_dir.exists():
            return None
        return experiments_dir

    @staticmethod
    def _load_experiment_config(exp_dir: Path) -> Optional[dict]:
        cfg_path = exp_dir / 'config.json'
        if not cfg_path.exists():
            return None
        try:
            with open(cfg_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"  Warning: Could not read config for {exp_dir.name}: {e}")
            return None

    @staticmethod
    def _matches_request(cfg: dict, model_name: str, municipio: str) -> bool:
        cfg_model = str(cfg.get('model', '')).strip().lower()
        cfg_municipio = str(cfg.get('municipio', '')).strip().lower()
        return (cfg_model == str(model_name).strip().lower()) and (cfg_municipio == str(municipio).strip().lower())

    @staticmethod
    def _select_experiment_dirs(exp_dirs: List[Path], model_name: str, municipio: str) -> List[Path]:
        """
        Prefer experiments whose config.json matches requested model+municipio.
        Fall back to all experiments for legacy directories with missing/invalid config.
        """
        strict_matches = []
        for exp_dir in exp_dirs:
            cfg = ModelFinder._load_experiment_config(exp_dir)
            if cfg and ModelFinder._matches_request(cfg, model_name, municipio):
                strict_matches.append(exp_dir)
        if strict_matches:
            return strict_matches
        print(
            f"  Warning: No experiment with config model={model_name}, municipio={municipio}. "
            "Falling back to legacy selection by files."
        )
        return exp_dirs

    @staticmethod
    def _expected_fold_count(municipio: str) -> int:
        """
        Expected number of folds for a municipio split.
        Uses train_val_stream/<municipio>/train-*.txt.
        """
        train_dir = config.PROJECT_ROOT / 'train_val_stream' / str(municipio)
        if not train_dir.exists():
            return 0
        return len(list(train_dir.glob('train-*.txt')))
    
    @staticmethod
    def detect_model_type(model_path: Path) -> str:
        """
        Detect the model type (TabCmpt or MLP) by examining the state_dict keys.
        
        Args:
            model_path: Path to the .pth model file
            
        Returns:
            str: 'TabCmpt', 'MLP', or 'unknown'
        """
        try:
            import torch
        except ImportError:
            return 'unknown'
        
        try:
            state_dict = torch.load(model_path, map_location='cpu')
            keys = list(state_dict.keys())
            
            # TabCmpt has these specific keys
            if any('attentive_transformer' in k for k in keys) or any('mlp_steps' in k for k in keys):
                return 'TabCmpt'
            # MLP has simpler structure with 'base' or 'network' or 'fc'
            elif any('base' in k for k in keys) or any('network' in k for k in keys):
                return 'MLP'
            else:
                return 'unknown'
        except Exception as e:
            print(f"  Warning: Could not detect model type: {e}")
            return 'unknown'
    
    @staticmethod
    def find_latest_model(model_name: str = 'TabCmpt', municipio: str = 'blockCV') -> Tuple[Optional[Path], Optional[str], Optional[str]]:
        """
        Find the most recent trained model file, ensuring it matches the requested model type.
        
        Args:
            model_name: Name of the model type ('TabCmpt', 'MLP', etc.)
            municipio: Municipality name for model file matching
        
        Returns:
            tuple: (model_path, timestamp, detected_model_type) or (None, None, None) if not found
        """
        experiments_dir = ModelFinder._get_experiments_dir()
        if not experiments_dir:
            print(f"  ⚠️  Experiments directory not found: {experiments_dir}")
            return None, None, None
        
        # Find all experiment directories
        exp_dirs = [d for d in experiments_dir.iterdir() if d.is_dir()]
        
        if not exp_dirs:
            print(f"  ⚠️  No experiment directories found in {experiments_dir}")
            return None, None, None
        
        # Sort by modification time (most recent first), then filter by requested model+municipio.
        exp_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        exp_dirs = ModelFinder._select_experiment_dirs(exp_dirs, model_name, municipio)
        
        print(f"  Searching for {model_name} model (municipio: {municipio})")
        print(f"  Found {len(exp_dirs)} experiment directories")
        
        # Collect all candidate models across all directories
        candidates = []
        
        for exp_dir in exp_dirs:
            if model_name in ['TabCmpt', 'MLP']:
                # First try exact match with municipio name
                model_path = exp_dir / f'{municipio}.pth'
                if model_path.exists():
                    detected_type = ModelFinder.detect_model_type(model_path)
                    if detected_type == model_name or detected_type == 'unknown':
                        timestamp = exp_dir.name
                        mtime = model_path.stat().st_mtime
                        candidates.append((model_path, timestamp, detected_type, mtime))
                        print(f"  Found exact match: {model_path.name} in {timestamp} (type: {detected_type})")
                
                # Also collect all .pth files for fallback
                pth_files = list(exp_dir.glob('*.pth'))
                for pth_file in pth_files:
                    if pth_file.name != f'{municipio}.pth':  # Don't duplicate exact match
                        detected_type = ModelFinder.detect_model_type(pth_file)
                        if detected_type == model_name:
                            timestamp = exp_dir.name
                            mtime = pth_file.stat().st_mtime
                            candidates.append((pth_file, timestamp, detected_type, mtime))
            else:
                # For sklearn models, look for .pkl files
                model_path = exp_dir / f'{municipio}.pkl'
                if model_path.exists():
                    timestamp = exp_dir.name
                    mtime = model_path.stat().st_mtime
                    candidates.append((model_path, timestamp, model_name, mtime))
                
                pkl_files = list(exp_dir.glob('*.pkl'))
                for pkl_file in pkl_files:
                    if pkl_file.name != f'{municipio}.pkl':
                        timestamp = exp_dir.name
                        mtime = pkl_file.stat().st_mtime
                        candidates.append((pkl_file, timestamp, model_name, mtime))
        
        if not candidates:
            print(f"  ⚠️  No {model_name} models found")
            return None, None, None
        
        # Sort candidates by file modification time (most recent first)
        # This ensures we get the latest model even if it's in an older experiment directory
        candidates.sort(key=lambda x: x[3], reverse=True)
        
        # Return the most recent matching model
        model_path, timestamp, detected_type, _ = candidates[0]
        print(f"  ✓ Selected model: {model_path.name} from {timestamp} (type: {detected_type})")
        
        return model_path, timestamp, detected_type

    @staticmethod
    def find_all_fold_models_in_latest_experiment(model_name: str = 'TabCmpt', municipio: str = 'blockCV') -> Tuple[Optional[str], List[Path]]:
        """
        Find the latest experiment dir and return ALL fold model paths in it (for multi-fold averaging).
        Reduces "all points = 1" in whole regions by averaging over folds.
        
        Returns:
            (timestamp, list of model paths) or (None, []) if not found.
        """
        experiments_dir = ModelFinder._get_experiments_dir()
        if not experiments_dir:
            return None, []
        exp_dirs = [d for d in experiments_dir.iterdir() if d.is_dir()]
        if not exp_dirs:
            return None, []
        exp_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        exp_dirs = ModelFinder._select_experiment_dirs(exp_dirs, model_name, municipio)
        expected_folds = ModelFinder._expected_fold_count(municipio)

        # First pass: require complete fold set when expected fold count is known.
        for exp_dir in exp_dirs:
            timestamp = exp_dir.name
            if model_name in ['TabCmpt', 'MLP']:
                pth_files = sorted(list(exp_dir.glob('*.pth')))
                if pth_files:
                    if expected_folds > 0 and len(pth_files) < expected_folds:
                        print(
                            f"  Skipping incomplete experiment {timestamp}: "
                            f"{len(pth_files)}/{expected_folds} fold models found"
                        )
                        continue
                    return timestamp, pth_files
            else:
                pkl_files = sorted(list(exp_dir.glob('*.pkl')))
                if pkl_files:
                    if expected_folds > 0 and len(pkl_files) < expected_folds:
                        print(
                            f"  Skipping incomplete experiment {timestamp}: "
                            f"{len(pkl_files)}/{expected_folds} fold models found"
                        )
                        continue
                    return timestamp, pkl_files

        # Second pass fallback: if no complete run exists, return the best available run.
        best_timestamp = None
        best_paths: List[Path] = []
        for exp_dir in exp_dirs:
            if model_name in ['TabCmpt', 'MLP']:
                paths = sorted(list(exp_dir.glob('*.pth')))
            else:
                paths = sorted(list(exp_dir.glob('*.pkl')))
            if len(paths) > len(best_paths):
                best_paths = paths
                best_timestamp = exp_dir.name
        if best_paths:
            print(
                f"  Warning: No complete experiment found for model={model_name}, municipio={municipio}. "
                f"Using best available incomplete run {best_timestamp} with {len(best_paths)} fold model(s)."
            )
            return best_timestamp, best_paths
        return None, []