"""
Load train_municipios to match the scaler used during model training.
Used by recalculate_and_predict and ec2_worker to align EventDB scaler with training.
"""
import os
import json
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional


def _resolve_paths():
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(backend_dir)
    train_val_dir = os.path.join(project_root, 'train_val_stream')
    experiments_dir = os.path.join(project_root, 'experiments')
    # Fallback: try cwd
    if not os.path.exists(project_root):
        project_root = os.getcwd()
        train_val_dir = os.path.join(project_root, 'train_val_stream')
        experiments_dir = os.path.join(project_root, 'experiments')
    return project_root, train_val_dir, experiments_dir


def _norm_municipio_key(s: str) -> str:
    """
    Normalize municipio strings so filenames and text-file contents match reliably
    across OS/filesystems (notably macOS unicode normalization).
    """
    if s is None:
        return ""
    # Normalize unicode (e.g., CÓRDOBA may be NFC in files, NFD in filenames)
    s = unicodedata.normalize("NFC", str(s))
    # Normalize whitespace/case
    s = " ".join(s.strip().split())
    return s.upper()


def resolve_municipio_split_for_experiment(timestamp, municipio_from_request):
    """
    Resolve the train_val_stream split name used by the experiment.
    """
    _, _, experiments_dir = _resolve_paths()
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
    return municipio_for_train


def _load_train_file(train_file: str) -> Optional[List[str]]:
    if not os.path.exists(train_file):
        return None
    train_municipios = []
    with open(train_file, 'r') as f:
        for line in f:
            name = line.strip()
            if name:
                train_municipios.append(name)
    if train_municipios:
        return train_municipios
    return None


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
    _, train_val_dir, _ = _resolve_paths()
    municipio_for_train = resolve_municipio_split_for_experiment(timestamp, municipio_from_request)

    train_file = os.path.join(train_val_dir, municipio_for_train, 'train-0.txt')
    train_municipios = _load_train_file(train_file)
    if train_municipios:
        print(f"  Loaded {len(train_municipios)} train_municipios from train_val_stream/{municipio_for_train}/train-0.txt")
        return train_municipios

    # Fallback strategy (avoid silent 3-municipio legacy behavior):
    # - If split directory exists, union all municipios from train-*.txt.
    # - Otherwise, raise a clear error so caller can surface it.
    split_dir = Path(train_val_dir) / str(municipio_for_train)
    if split_dir.exists():
        union: List[str] = []
        seen = set()
        for p in sorted(split_dir.glob("train-*.txt")):
            vals = _load_train_file(str(p)) or []
            for v in vals:
                k = _norm_municipio_key(v)
                if k and k not in seen:
                    union.append(v)
                    seen.add(k)
        if union:
            print(
                f"  Fallback: train-0 missing; using union of train-*.txt "
                f"from train_val_stream/{municipio_for_train}/ ({len(union)} municipios)"
            )
            return union

    raise FileNotFoundError(
        "Could not load train_municipios for repredict. "
        f"Missing split files at {split_dir} (expected train-0.txt at {train_file})."
    )


def load_train_municipios_for_fold(timestamp, municipio_from_request, fold_model_path):
    """
    Load train_municipios for the specific fold model file.
    For experiments produced by main.py, fold files are named by validation municipio
    (e.g. ABEJORRAL.pkl), so we map val-*.txt -> fold index -> train-<idx>.txt.
    Falls back to train-0 behavior if mapping is unavailable.
    """
    _, train_val_dir, _ = _resolve_paths()
    municipio_for_train = resolve_municipio_split_for_experiment(timestamp, municipio_from_request)
    split_dir = Path(train_val_dir) / str(municipio_for_train)
    stem_raw = Path(str(fold_model_path)).stem
    stem = _norm_municipio_key(stem_raw)

    # Build val_municipio -> fold_idx map from val-*.txt
    val_to_fold: Dict[str, str] = {}
    if split_dir.exists():
        for val_file in sorted(split_dir.glob('val-*.txt')):
            idx = val_file.stem.replace('val-', '')
            try:
                with open(val_file, 'r') as f:
                    first = ''
                    for line in f:
                        line = line.strip()
                        if line:
                            first = line
                            break
                if first:
                    val_to_fold[_norm_municipio_key(first)] = idx
            except Exception:
                continue

    fold_idx = val_to_fold.get(stem)
    if fold_idx is not None:
        train_file = split_dir / f"train-{fold_idx}.txt"
        fold_train_municipios = _load_train_file(str(train_file))
        if fold_train_municipios:
            print(
                f"  Loaded fold-specific train_municipios for '{stem}' "
                f"from train_val_stream/{municipio_for_train}/train-{fold_idx}.txt "
                f"({len(fold_train_municipios)} municipios)"
            )
            return fold_train_municipios

    # Fallback to train-0 logic
    sample_keys = list(val_to_fold.keys())[:5]
    print(
        "  Warning: Could not resolve fold-specific train file for model "
        f"'{stem_raw}' (normalized='{stem}'). Using train-0 fallback. "
        f"Example normalized val keys: {sample_keys}"
    )
    return load_train_municipios_for_repredict(timestamp, municipio_from_request)
