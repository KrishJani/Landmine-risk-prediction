"""
Load train_municipios to match the scaler used during model training.
Used by recalculate_and_predict and ec2_worker to align EventDB scaler with training.
"""
import os
import json


def load_train_municipios_for_repredict(timestamp, municipio_from_request):
    """
    Load train_municipios to match the scaler used during model training.
    Reads experiments/{timestamp}/config.json for the municipio used during training,
    then loads train_val_stream/{municipio}/train-0.txt. Falls back to request municipio
    or hardcoded list if files are missing.

    Args:
        timestamp: Experiment directory name (e.g. from ModelFinder)
        municipio_from_request: Municipio from the API request (e.g. 'map_included', 'blockCV')

    Returns:
        List of municipio names to use for EventDB train_municipios
    """
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(backend_dir)
    train_val_dir = os.path.join(project_root, 'train_val_stream')
    experiments_dir = os.path.join(project_root, 'experiments')
    # Fallback: try cwd
    if not os.path.exists(project_root):
        project_root = os.getcwd()
        train_val_dir = os.path.join(project_root, 'train_val_stream')
        experiments_dir = os.path.join(project_root, 'experiments')

    municipio_for_train = municipio_from_request
    config_path = os.path.join(experiments_dir, str(timestamp or ''), 'config.json')
    if timestamp and os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                cfg = json.load(f)
            municipio_for_train = cfg.get('municipio', municipio_from_request)
            print(f"  Using train_municipios from experiment config: municipio={municipio_for_train}")
        except Exception as e:
            print(f"  Could not read config.json: {e}, using municipio from request")

    train_file = os.path.join(train_val_dir, municipio_for_train, 'train-0.txt')
    if os.path.exists(train_file):
        train_municipios = []
        with open(train_file, 'r') as f:
            for line in f:
                name = line.strip()
                if name:
                    train_municipios.append(name)
        if train_municipios:
            print(f"  Loaded {len(train_municipios)} train_municipios from train_val_stream/{municipio_for_train}/train-0.txt")
            return train_municipios

    # Fallback to hardcoded list (legacy behavior)
    fallback = ['BOLÍVAR', 'MURINDÓ', 'PUERTO LIBERTADOR']
    print(f"  Fallback: using hardcoded train_municipios (train file not found at {train_file})")
    return fallback
