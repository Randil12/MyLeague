# Supervision VPS et Airflow

## Activation sur le VPS Linux après push/pull

Airflow doit avoir déjà initialisé/migré sa base et être démarré.
Le mot de passe existant `DATA_ANALYST_PASSWORD` est réutilisé pour un rôle dédié
`airflow_monitor` dans la base Airflow ; aucun secret n’est ajouté au dépôt.

```bash
docker compose --profile monitoring run --rm airflow-monitor-init
docker compose --profile monitoring up -d prometheus node-exporter grafana
```

Ne pas activer node-exporter sur Docker Desktop pour mesurer Windows : il mesurerait
la VM Linux Docker. Le profil cible le VPS Linux. Les commandes habituelles sans ce
profil continuent de fonctionner. Après une modification de configuration Prometheus :

```bash
docker compose --profile monitoring restart prometheus grafana
```

Le script CI/CD existant ne démarre pas automatiquement ce profil : l’activer avec
les commandes ci-dessus. Les services démarrés redémarrent avec Docker (`unless-stopped`).
Après changement du mot de passe ou des vues SQL, relancer `airflow-monitor-init`.

## Tableaux de bord dans le dossier MyLeague

- **VPS · CPU RAM disque** : CPU, RAM disponible/utilisée, charge par CPU,
  espace disponible et pourcentage occupé par montage, collecteurs et alertes.
- **Airflow · DAG tâches et scheduler** : dernier run par DAG, pause, états des
  tâches du dernier run, durée, derniers heartbeats par type de job, erreurs d’import,
  historique des runs sur sept jours. Un DAG sans run reste visible avec valeurs NULL.
  Des DAG obsolètes encore enregistrés dans Airflow peuvent apparaître.
- **Supervision des pipelines data** reste disponible et complémentaire.

Actualisation : 30 secondes. Les graphes CPU nécessitent quelques collectes.
Les tableaux SQL sont des lectures actuelles ; le filtre temporel Grafana ne change
pas les limites explicites des requêtes (dernier run / sept jours).
Les heartbeats ne constituent pas un test HTTP de disponibilité de l’interface Airflow.
Un scheduler/processor à l’état running avec heartbeat âgé de plusieurs minutes est suspect.
La supervision est indépendante du DAG de monitoring : un scheduler arrêté n’empêche pas
Grafana de lire ses dernières informations dans PostgreSQL.

## Alertes et limites

Prometheus évalue les seuils toutes les 30 secondes : CPU >90 % durant 10 minutes,
RAM disponible <10 % durant 5 minutes, disque disponible <15 % durant 5 minutes,
collecteur inaccessible durant 2 minutes. Les alertes apparaissent dans le dashboard.
Pas d’Alertmanager/contact email/Discord ajouté : aucune notification externe automatique.
Une panne totale du VPS rend aussi sa supervision indisponible ; un contrôle externe
reste nécessaire pour détecter ce cas.

La rétention Prometheus est de sept jours ou 1 GB de blocs, selon la première limite
atteinte. WAL et données actives prennent de la place en plus : ce n’est pas un quota disque.
Limites RAM : Prometheus 512 Mio, node-exporter 128 Mio. Les données persistent dans
le volume `prometheus_data`. Aucun port supplémentaire n’est publié.

Le collecteur monte la racine du VPS en lecture seule et utilise son espace PID pour
mesurer l’hôte. Il n’est pas privilégié et ne reçoit pas de montage dédié du socket Docker.
Cela donne une visibilité sur l’hôte : activer uniquement sur une machine administrée.
Cette version mesure **le VPS**, pas les consommations CPU/RAM de chaque conteneur.

Grafana utilise un rôle limité aux vues `monitoring` de la base Airflow : aucun accès
aux connexions, variables, XCom, configuration ou traces d’erreurs détaillées.
Les noms de DAG, tâches agrégées et fichiers restent des informations internes.
Le SQL cible le schéma de métadonnées Airflow 3 de ce projet ; vérifier après migration.

## Vérification

```bash
docker compose --profile monitoring ps
docker compose --profile monitoring logs --tail=50 prometheus node-exporter
docker compose exec -T postgres psql -U airflow -d airflow -c "SELECT * FROM monitoring.job_heartbeats;"
```

Dans Grafana, tester les sources **VPS Prometheus** et **Airflow Monitoring**.
Conserver l’accès existant par tunnel SSH, par exemple `http://localhost:13000`.
Un panneau vide ou une erreur de source n’est pas une preuve de bonne santé.

Références : [Node Exporter](https://github.com/prometheus/node_exporter),
[rétention Prometheus](https://prometheus.io/docs/prometheus/latest/storage/).
