# map_included split

This split includes **all** municipalities that appear in the map (resolution_0.5.csv and DB), so the model sees CARTAGENA DE INDIAS, CÓRDOBA, PUERTO LIBERTADOR, SAN JUAN NEPOMUCENO, SANTA ROSA DEL SUR, ZAMBRANO during training and does not collapse to constant 0/1 on them.

- 21 folds (one municipality held out for validation per fold).
- Use with: `--municipio map_included` when training (e.g. in ec2_worker_main or main.py).
