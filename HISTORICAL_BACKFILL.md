# Rattrapage historique nocturne

`riot_historical_backfill` tourne à **01:35 UTC chaque jour** (03:35 à Paris en
été, 02:35 en hiver). `catchup=False`, un seul run simultané, aucun retry Airflow.
La collecte régulière de minuit a une fenêtre normale de 90 minutes ; des
relances manuelles ou retries peuvent toutefois chevaucher le backfill.
Le live reste indépendant : ce planning n'est pas un quota Riot global.

## Limites et reprise

- Jusqu'à 10 joueurs par run, priorité club/academy, puis fenêtres déjà entamées
  (les moins récemment avancées d'abord), puis nouveaux joueurs. Cela évite de
  laisser une page inachevée derrière des milliers de nouveaux comptes.
- Fenêtre fixe des 60 jours précédant la première prise en charge de chaque joueur.
- Pages de 100 identifiants, offset conservé dans PostgreSQL.
- Au plus 500 tentatives de traitement de matchs/timelines ; un nouveau match
  avec sa timeline représente jusqu'à deux appels, en plus des listes et retries.
- Budget souple 35 minutes, arrêt forcé de la tâche à 40 minutes, DAG à 55 minutes.
- Après interruption, la page non terminée est reprise ; les matchs déjà réussis
  sont dédupliqués. Une timeline manquante peut être récupérée seule.
- Une fenêtre complète n'est plus rescannée : les nouveaux matchs restent à la
  charge de `riot_euw_ingestion`. Une nouvelle campagne historique nécessite une
  décision explicite, pas une suppression automatique des checkpoints.
- Un `success` de run indique un lot réussi, pas la couverture de tous les joueurs.
  Les matchs devenus indisponibles chez Riot restent impossibles à récupérer.

## PostgreSQL et MinIO

`audit.riot_historical_progress` est créée automatiquement au premier lancement.
Elle conserve début/fin de fenêtre, offset et indicateur de complétude. Le curseur
`last_match_ingestion_at` de la collecte incrémentale n'est jamais modifié.
Un verrou PostgreSQL empêche deux backfills concurrents.

Les pages sont archivées sous `bronze/riot/region=euw1/historical_match_ids/`.
Les matchs et timelines réutilisent les chemins existants, basés sur le match ID.
Aucun bucket, schéma ou objet existant n'est supprimé. Aucune rétention automatique
n'est activée sans choix de durée et sauvegarde vérifiée.

La tâche suivante charge Bronze vers les tables `raw`. Les builds `dbt_transform`
existants publient les données Gold : celui de 02:00 peut précéder la fin du
backfill ; le suivant est à 05:00 UTC. Des index gérés par dbt sont ajoutés sur
les faits Riot (joueur/date, patch/joueur, match/équipe) et pro (année/joueur,
unicité match/joueur).

## Déploiement

Après push/pull, redémarrer Airflow lorsqu'aucune tâche importante n'est en cours,
puis activer le DAG. Les droits sur `airflow/logs` doivent déjà être corrigés.
Lancer `dbt_transform` et `leaguepedia_ingestion` pour appliquer les index lors des
reconstructions Gold. Pas de migration manuelle ni de recréation des volumes.

```bash
docker compose restart airflow
```

Suivi (dans PostgreSQL Gold) :

```sql
SELECT completed, count(*) FROM audit.riot_historical_progress GROUP BY completed;
SELECT pipeline_name, status, started_at, ended_at, records_written, error_count
FROM audit.pipeline_runs WHERE pipeline_name = 'riot_historical_backfill'
ORDER BY started_at DESC LIMIT 10;
```

Ces changements ne corrigent pas à eux seuls la couverture des durées Leaguepedia,
les tables patch notes vides ou l'activation du roster sur le VPS : ces points
restent des chantiers distincts, sans suppression de données pour les masquer.
