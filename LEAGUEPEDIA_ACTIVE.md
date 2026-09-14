# Joueurs actifs et parties compétitives de l'année

Le DAG fusionné `leaguepedia_ingestion` démarre à **HH:15 UTC, chaque heure**.
Il collecte les parties Leaguepedia de l'année UTC courante, puis lance un
`dbt build` ciblé avec tests. Ce n'est ni de la solo queue Riot ni du temps réel.

## Périmètre et limites

« Actif dans l'année » = au moins une participation compétitive observée dans
Leaguepedia cette année. Cela ne prouve pas un contrat professionnel actuel :
la source couvre aussi des compétitions semi-professionnelles/amateurs. Aucune
promesse d'exhaustivité mondiale. Les joueurs sans scoreboard ne sont pas inclus.
L'identité affichée est le `Link` Leaguepedia, pas le PUUID ni le nom civil.
Les anciens alias/renommages ne sont pas encore consolidés via PlayerRedirects.

## Collecte et reprise

- Réutilise les identifiants Leaguepedia, PostgreSQL et MinIO déjà configurés.
  Aucune nouvelle clé ni aucun bucket requis. Le paramètre historique
  `LEAGUEPEDIA_YEAR` n'affecte pas ce DAG : il suit automatiquement l'année UTC.
- Les deux derniers jours sont rafraîchis en priorité, puis les journées
  manquantes depuis janvier. Les anciennes journées sont revisitées au plus tôt
  après 24 h pour intégrer les corrections tardives.
- Maximum 20 journées par passage, budget souple de 10 minutes (vérifié entre
  journées), limite Airflow de 25 minutes par tentative de collecte.
  Le premier chargement peut nécessiter plusieurs passages ; pas de date de
  complétude garantie. `catchup=False`, une seule exécution active et verrou SQL.
- Pagination saturée : découpage de la fenêtre, jamais de troncature acceptée.
- Bronze avant raw ; checkpoint uniquement après chargement complet de la journée.
  Les upserts rendent les reprises idempotentes en base. Une suppression dans
  Leaguepedia n'efface pas automatiquement l'ancienne ligne raw.
- MinIO conserve les snapshots sous
  `bronze/leaguepedia/{scoreboard_games,scoreboard_players}/run_id=yearly-.../day=.../`.
  Les snapshots répétés consomment du stockage : surveiller le bucket et définir
  une politique de rétention selon les besoins de preuve. Si MinIO n'est pas
  configuré, le collecteur existant utilise le stockage local de secours.

Le DAG fusionné enchaîne l'historique annuel, les référentiels joueurs/équipes/
tournois puis le build Gold, sans tâches parallèles. Le DAG dbt général
exclut le tag `leaguepedia_active` pour éviter deux constructions concurrentes
de ces tables. Le DAG horaire possède ses propres logs/artéfacts dbt dans `/tmp`.

## Limitation Cargo

Le compte a exposé `cargo-query: 60 hits / 60 seconds`. Tous les appels Cargo
du client (pages, sondes de pagination, référentiels, reprises) sont espacés
d'au moins 2 secondes après la fin de l'appel précédent, soit au plus environ
30 appels/minute dans le processus. Sur `ratelimited`, la même page est retentée
après 60, 120 puis 240 secondes. Après trois reprises infructueuses, l'erreur
remonte ; pas de retry Airflow immédiat, reprise au prochain passage horaire.
Les autres erreurs ne sont pas retentées par ce mécanisme.

Ce limiteur est local au processus, pas distribué entre machines. Ne pas lancer
de collecte CLI ni une autre installation utilisant le même compte en parallèle.
La fusion, `max_active_runs=1` et `max_active_tasks=1` évitent le cumul des DAGs.
Une limitation Fandom supplémentaire reste possible.

## Tables Gold

- `gold.gold_pro_player_games` : une participation par partie/joueur, équipe de
  la partie, rôle, champion, patch source, résultat et statistiques disponibles.
- `gold.gold_pro_active_players_year` : annuaire par année, nombre de parties,
  pool de champions, premières/dernières parties et taux de victoire.
- `gold.gold_pro_player_comparison` : agrégats par année/joueur/patch/rôle/champion.
  Toujours comparer les tailles d'échantillon. Le KDA est un ratio de sommes des
  lignes complètes ; sans mort, NULL. Les résultats/stats absents ne valent pas 0.
  CS et or sont des valeurs de fin de partie, pas des valeurs par minute.

Ces tables conservent toutes les années déjà chargées ; filtrer `season_year`.
L'espace **Comparaison pro** exploite ces participations pour comparer deux joueurs
sur un même périmètre. Voir [PRO_COMPARISON.md](PRO_COMPARISON.md) pour les filtres,
les champs supplémentaires et la limite explicite de Gold@15.

## Déploiement et validation

Après merge et déploiement CI/CD (ou pull puis redémarrage Airflow), attendre
que les deux DAGs Leaguepedia soient reparsés. Mettre les anciens DAGs en pause
et attendre la fin des collectes déjà lancées avant le changement (la pause ne
stoppe pas une tâche en cours). Garder `leaguepedia_active_players` en pause :
son fichier conserve un DAG sans planning et sans appels API, uniquement pour
la transition. Activer seulement `leaguepedia_ingestion` dans Airflow et
déclencher un premier passage manuel si souhaité. Le dbt ciblé est automatique.

La sortie de `collect_current_year` indique `days_remaining` et
`coverage_complete_as_observed`. Une collecte réussie peut être encore partielle.
Le checkpoint persiste dans `audit.leaguepedia_year_days` et les exécutions dans
`audit.pipeline_runs` avec `pipeline_name='leaguepedia_ingestion'`.

```sql
SELECT * FROM gold.gold_pro_active_players_year
WHERE season_year = extract(year FROM now() AT TIME ZONE 'UTC')
ORDER BY games DESC;

SELECT * FROM gold.gold_pro_player_comparison
WHERE season_year = extract(year FROM now() AT TIME ZONE 'UTC') AND games >= 5
ORDER BY games DESC;
```

Tests unitaires sans réseau : `pytest tests/test_leaguepedia*.py`.
Le nouveau test `tests/integration/test_leaguepedia_active.py` est exécuté par
la CI existante : vrai PostgreSQL, MinIO et dbt ; seule l'API externe est simulée.
