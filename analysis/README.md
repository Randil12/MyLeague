# Analyse statistique du Bloc 2

Ce dossier contient l'analyse reproductible utilisée dans le dossier RNCP Bloc 2.

Pré-requis :

```bash
pip install -r requirements-analysis.txt
docker compose up -d gold-postgres
python analysis/statistical_analysis.py
```

Le script lit uniquement les tables `gold`, sélectionne automatiquement le patch
le plus récent et produit :

- `analysis/results/statistical_analysis_results.json` : résultats chiffrés et décisions ;
- `docs/assets/bloc2/draft_priorities.png` : priorités de draft ;
- `docs/assets/bloc2/solo_vs_pro_presence.png` : comparaison solo/pro ;
- `docs/assets/bloc2/patch_change_effect.png` : test de l'effet des changements ;
- `docs/assets/bloc2/patch_evolution.png` : principales évolutions de winrate.

La connexion locale utilise `127.0.0.1:5433`. Elle peut être modifiée avec
`ANALYSIS_POSTGRES_HOST` et `ANALYSIS_POSTGRES_PORT`. Les identifiants sont lus
depuis `.env` sans jamais être écrits dans les résultats.
