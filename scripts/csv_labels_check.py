"""Quick check of mines_outcome labels per municipality in resolution_0.5.csv. Run from project root: python scripts/csv_labels_check.py"""
import os
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(PROJECT_ROOT, 'processed_dataset', 'resolution_0.5.csv')
df = pd.read_csv(path)
if 'mines_outcome' in df.columns:
    print(
        df.groupby('Municipio')['mines_outcome']
        .agg(['sum', 'count'])
        .rename(columns={'sum': 'positives', 'count': 'total'})
    )
else:
    print("Column 'mines_outcome' not found. Columns:", list(df.columns))
