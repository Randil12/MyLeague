# Mise à jour : plans enregistrés et match-ups v2

Le repère `training-plans-matchups-v2` est affiché en pied de page et dans
`/healthz` (champ `app_version`). Il identifie les fonctionnalités, pas un SHA Git.

Les nouveaux plans sont présents dans `frontend/src/TrainingPlan.tsx`,
montés uniquement dans Entraînement. Coaching conserve `LaneAnalysis`.
Si l’ancien écran apparaît sans ce repère, vérifier la version de l’image web,
le commit réellement déployé et le port/tunnel utilisé, pas seulement les fichiers du VPS.
La page HTML d’entrée n’est plus mise en cache ; les assets restent nommés par leur hash.

Après push, fusion et pull de la bonne version, sur le VPS :

```bash
docker compose up -d --build web riot-live
docker compose restart airflow
docker compose exec -T web python -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8501/healthz')))"
```

Attendre la fin des DAG dbt/Leaguepedia déjà en cours, puis reconstruire les modèles
(ou lancer `dbt_transform` et `leaguepedia_ingestion` dans Airflow) :

```bash
docker compose exec -T airflow dbt build \
  --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt/profiles \
  --target dev --select +gold_player_lane tag:leaguepedia_active \
  --indirect-selection cautious \
  --target-path /tmp/dbt-web-update/target --log-path /tmp/dbt-web-update/logs
```

Le déploiement CI reconstruit les images mais ne reconstruit pas les tables dbt.
Les nouvelles colonnes de lane doivent exister pour l’API match-ups.
Le redémarrage de riot-live initialise les tables des plans de progression.

## Périmètre des corrections

- `BrokenBIade` (I majuscule) → `BrokenBlade` (l minuscule) : correspondance
  explicite pour les participations G2 Esports de 2026 observées dans la base.
  Hypothèse de correction liée à ce roster, pas une règle générale de similarité.
  123 + 5 participations donnent 128 ; un doublon du même match reste compté une fois.
  Les homonymes et les autres aliases ne sont pas fusionnés automatiquement.
- GD@15 : moyenne de l’écart d’or du champion étudié moins son adversaire au même rôle,
  avec nombre de parties renseignées.
- Solo kills : totaux et moyennes par partie, A tue B et B tue A sans assistance
  enregistrée, pour la partie entière. Les kills contre d’autres joueurs sont exclus.
  Les événements JSON identiques sont dédupliqués et les exécutions sans joueur tueur exclues.
  Cela ne prouve pas un duel isolé ; les rôles déclarés ne décrivent pas tous les lane swaps.
- Couverture : première frame <=1 seconde, pas d’écart >90 secondes, tableaux d’événements
  présents et dernière frame atteignant la durée de partie à 5 secondes près.
  Sans cette couverture ou avec un adversaire de rôle ambigu, les solo kills restent NULL.

Ces changements concernent la vue Match-ups SoloQ de l’application. Les métriques ne sont
pas ajoutées artificiellement aux parties Leaguepedia ni au résultat Spark existant.
