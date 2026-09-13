# Application : champions, joueurs et performances

## Changements

- Icônes officielles Data Dragon à partir de `reference.dim_champion` : nom,
  identifiant de champion et version existante (pas de patch d'image inventé).
  Le navigateur charge les images depuis le CDN Riot, autorisé explicitement
  dans la CSP. Repli texte si le référentiel ou l'image manque.
- Icônes partagées dans draft, exclusions pick/ban, adversaires, compositions,
  entraînement, historique individuel et compositions en direct.
- Formulaire Riot ID accessible en Entraînement et Coaching, en plus du direct.
  Liste partagée et persistante, capacité existante de 5 (maximum configurable 10).
  La suppression conserve l'historique. Le service technique `riot-live` reste
  seul responsable des écritures ; le rôle SQL du backend reste en lecture seule.
- Les joueurs ajoutés sont maintenant inscrits à la collecte de matchs (source
  `club`). Les membres déjà présents dans le roster sont migrés au démarrage de
  `riot-live`. Les sources ladder/Academy existantes sont préservées. Les joueurs
  club/Academy passent en priorité dans les lots de collecte Riot.
- Le sélecteur inclut les joueurs suivis et les participants ayant déjà des
  matchs Gold (maximum 5 000), avec recherche par pseudo, nombre de matchs et
  sélection initiale du dernier patch du joueur si aucun patch n'est imposé.
  Les PUUID restent des clés internes, jamais des pseudos de repli.
- Nouvel espace Classement EUW : jusqu'aux 300 Challenger observés dans le dernier
  snapshot Riot, LP, victoires, défaites, winrate et date de collecte. Un snapshot
  partiel/ancien n'est pas présenté comme un classement live exhaustif.
  Les égalités de LP sont triées par victoires puis clé interne, pas un rang officiel.
- Le snapshot `riot_euw_ingestion` résout les Riot ID Challenger via ACCOUNT-V1 :
  maximum 300 comptes par passage, cache 7 jours (`name_checked_at`), 2 secondes
  entre appels, budget de 12 minutes. Sur refus/quota, les noms déjà connus restent
  disponibles et le lot restant est reporté. Aucun appel Riot depuis le navigateur.
- Entraînement : pool réellement joué, volume, winrate, KDA, CS/min et pistes de
  revue VOD. Plus de dépendance exclusive aux maîtrises Academy. Les match-ups
  sont visibles dès un match avec avertissement de faible échantillon.
- Coaching : historique/progression individuels existants et nouveau tableau des
  cinq joueurs sélectionnés, même sans matchs communs. Le tableau individuel ne
  prétend pas mesurer les performances collectives ni les scrims.

## Mise en service

Déployer le code via la CI/CD existante : reconstruction de `web` et `riot-live`,
redémarrage Airflow. Aucun nouveau secret. Ne pas publier l'application privée
sans authentification : le formulaire modifie une liste partagée.

1. Vérifier `datadragon_ingestion` pour le référentiel des icônes.
2. Ajouter les joueurs par `Pseudo#TAG` dans l'application.
3. Exécuter/attendre `riot_euw_ingestion` (snapshot, noms, matchs puis chargement raw).
4. Exécuter/attendre `dbt_transform`, puis actualiser l'application.

Un nouveau joueur ne dispose pas immédiatement de statistiques. Le collecteur
reste borné par la fenêtre, le nombre de matchs et les quotas Riot existants.
Les noms non encore résolus affichent « Pseudo indisponible », pas un identifiant.
Les icônes peuvent différer des versions historiques : dernière version du référentiel.

Tests : endpoints simulés/unitaires et tests PostgreSQL dans
`tests/integration/test_app_performance.py`, exécutés par la CI isolée.
