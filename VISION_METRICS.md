# Wards : entraînement et coaching individuel

Les compteurs sont extraits des participants du JSON Match-V5 déjà conservé
dans `raw.riot_matches`, puis exposés par `gold.gold_player_lane` et `/api/lane`.
L'accès reste limité au roster du coach. Aucune nouvelle requête Riot n'est
nécessaire pour les parties dont les champs sont déjà présents.

| Champ Riot | Colonne Gold | Signification |
| --- | --- | --- |
| wardsPlaced | wards_placed | Compteur Riot de wards posées |
| detectorWardsPlaced | control_wards_placed | Balises de contrôle posées |
| visionWardsBoughtInGame | control_wards_bought | Balises de contrôle achetées |

Ne pas additionner ces compteurs, ni déduire les poses des achats. Les valeurs
absentes ou invalides restent NULL ; un zéro explicite est conservé. Les moyennes
et totaux portent sur les valeurs renseignées, avec couverture affichée.
Les timelines ne sont pas nécessaires. Aucun compteur professionnel Leaguepedia
n'est inventé à partir des données SoloQ.

En entraînement : joueur et patch sélectionnés (tous les patches par défaut).
En coaching individuel : mêmes filtres, plus rôle, champion et date du diagnostic.
Les totaux portent sur tout le périmètre, pas seulement la page d'historique.

## Déploiement VPS après récupération du code

1. Reconstruire Gold (ou relancer le DAG `dbt_transform`) :

```bash
docker compose exec -T airflow dbt build --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt/profiles --target dev --select +gold_player_lane --indirect-selection cautious --target-path /tmp/myleague-vision-target --log-path /tmp/myleague-vision-logs
```

2. Reconstruire l'application :

```bash
docker compose up -d --build web
```

3. Actualiser la page, sélectionner un joueur suivi et vérifier la couverture.
Sans reconstruction Gold, les nouvelles valeurs seront indisponibles.

## Tests

`frontend/tests/vision.test.mjs` : moyenne, valeurs absentes, vrai zéro.
`tests/integration/test_lane_metrics.py` : exécution SQL du modèle avec compteurs
distincts, absence de timeline, valeurs absentes/invalides et zéros.
