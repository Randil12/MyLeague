# Spectator continu — quasi-temps réel

Service Python Docker `riot-live`, indépendant d'Airflow. Il interroge spectator-v5
pour les joueurs suivis EUW, Academy d'abord. Par défaut : **5 joueurs**, un cycle
cible toutes les **60 secondes**, au moins une seconde entre joueurs.
Le temps de traitement, les erreurs et quotas peuvent allonger cette cadence.

## Déploiement VPS

Après push/pull, mettre en pause l'ancien DAG et attendre la fin de tout run
spectator déjà démarré avant d'activer le service :

```bash
cd /home/ubuntu/MyLeague
git pull origin dev
docker compose exec airflow airflow dags pause riot_live_spectator
docker compose restart airflow
docker compose up -d --build riot-live web
docker compose ps riot-live web
docker compose logs --tail=50 riot-live
```

Le DAG n'est plus planifié et sa tâche est désormais ignorée, mais son historique
reste visible. L'ancienne commande Python manuelle et le nouveau service utilisent
un verrou PostgreSQL commun : un seul collecteur peut tourner à la fois.
Ne pas démarrer des réplicas supplémentaires pour contourner les quotas.

Ouvrir **Coaching → En direct** avec le tunnel habituel vers le port VPS 8501.
L'écran recharge les observations toutes les 15 secondes quand l'onglet est visible,
sans déclencher d'appels Riot. Aucun build dbt n'est nécessaire pour ces vues live.

## Configuration

Les valeurs par défaut de Compose fonctionnent sans modifier le `.env` existant.
Pour les personnaliser, ajouter sur le VPS :

```dotenv
RIOT_LIVE_POLL_SECONDS=60
RIOT_LIVE_STREAM_MAX_PLAYERS=5
```

Cadence autorisée : 30 à 3600 secondes ; 1 à 10 joueurs. Le paramètre historique
`RIOT_LIVE_MAX_PLAYERS` du DAG n'est pas utilisé par le service.
Après changement, recréer le service : `docker compose up -d --force-recreate riot-live`.
Les clés Riot, PostgreSQL et MinIO existantes sont réutilisées ; aucune nouvelle
clé ni aucun port public ne sont ajoutés. La clé Riot doit permettre spectator-v5.

Les joueurs sont sélectionnés dans `audit.riot_tracked_players`, pas depuis la
liste des joueurs Leaguepedia. Enregistrer les joueurs Academy avec le workflow
existant si nécessaire. Si le nombre dépasse la limite, seuls les premiers de la
sélection stable sont suivis ; il n'y a pas de rotation garantie de tous les joueurs.

## Fiabilité et mesure

- `404` : aucune partie active renvoyée ; ne signifie pas que le joueur est déconnecté.
- Autre file que 420 : explicitement signalée, sans capture de composition.
- `429` : aucun autre appel du cycle, attente au moins égale au `Retry-After` Riot.
- `401/403` : pause d'au moins 15 minutes, état d'erreur visible. Vérifier/renouveler
  la clé puis recréer `riot-live` pour charger la nouvelle valeur.
- Autres erreurs : pause d'au moins une minute puis nouvelle tentative. Une erreur
  ne devient jamais une fausse confirmation de fin de partie.
- Après environ trois périodes (au moins trois minutes), l'observation est marquée
  périmée. Le statut global tient compte des pauses API annoncées.
- `checked_at` : réception de l'observation Riot ; `stored_at` : écriture SQL ;
  `request_ms` : durée de l'appel ; `storage_delay_ms` : observation → SQL.
  L'écran montre aussi son heure de rafraîchissement. Ce n'est pas une mesure du
  délai interne de publication de Riot ni une télémétrie de rendu persistée.

Le service partage la clé et les quotas avec les autres collectes Riot. Il respecte
son propre cooldown, mais ne coordonne pas globalement les quotas de tous les DAGs.
Ne pas abaisser la période sans observer les erreurs 429.

## Stockage et sécurité

Chaque nouvelle partie est archivée dans MinIO avant insertion SQL, puis dédupliquée
par game_id. État courant dans `raw.riot_live_player_state`, historique des parties
dans `raw.riot_live_game_snapshots`, état du service dans `audit.riot_live_service`.
Les créations sont idempotentes au démarrage, sans suppression des données existantes.

`gold.gold_live_players` et `gold.gold_live_service` sont des vues restreintes pour
`data_analyst` : ni payload brut, ni PUUID, ni clé observateur dans l'API. Les noms
des champions viennent de Data Dragon ; sinon leur identifiant est affiché.
L'interface reste privée par SSH, avec les mêmes limitations d'authentification.

Le collecteur utilise le compte technique Gold existant pour écrire. Seule l'API
utilise le compte lecture seule. Le conteneur est non-root, sans port exposé et avec
un système de fichiers en lecture seule (hors `/tmp` pour son signal de santé).
Le healthcheck vérifie la progression de la boucle, pas la validité de la clé API.
Docker ne redémarre pas automatiquement un conteneur simplement `unhealthy` ;
la boucle tente déjà de se reconnecter. Surveiller Docker et la vue En direct.

## Preuve pour l'oral

Faire jouer un joueur suivi en classé solo, observer la détection automatique,
les deux compositions et les horodatages, puis vérifier le changement d'état après
la partie. Conserver une capture des logs/écran sans secrets. Il s'agit de
**quasi-temps réel par polling**, pas d'un flux de positions, kills ou or en direct.
Une absence de match dans l'échantillon ou une restriction Riot peut empêcher la
démonstration ; ne pas présenter une simulation comme une partie live.
