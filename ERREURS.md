# Registre des erreurs et prévention des récidives — MyLeague

Ce document rassemble des incidents réellement signalés pendant le projet et les
contrôles à effectuer avant une nouvelle mise en production. Il ne remplace pas
les rapports de tests ni les preuves d'intervention sur le VPS.

Les statuts ci-dessous distinguent les résolutions confirmées dans les échanges,
les corrections présentes dans le dépôt et les diagnostics restant à confirmer.
Ne jamais joindre de mot de passe, clé API, clé SSH privée ou contenu complet du `.env`.

## Méthode commune de gestion d'incident

1. Noter l'heure, le service, le commit déployé, le DAG/run/tâche concernés et le symptôme.
2. Évaluer l'impact : service indisponible, données anciennes, collecte partielle ou erreur d'affichage.
3. Conserver les logs utiles avant redémarrage, en masquant les secrets et identifiants sensibles.
4. Tester une hypothèse à la fois avec des contrôles en lecture seule.
5. Appliquer la correction la plus ciblée, après sauvegarde si des données sont concernées.
6. Vérifier le résultat métier, pas seulement le démarrage du conteneur ou un statut HTTP 200.
7. Informer les utilisateurs du rétablissement et consigner une action préventive.

Communication à prévoir : prévenir le coach/staff des données retardées ou indisponibles,
transmettre les éléments techniques à la personne chargée de l'exploitation, puis annoncer
la clôture après validation. Ne pas présenter cette communication comme effectuée sans preuve.

## INC-01 — dbt échoue avec un code de sortie 2

**Symptôme observé :** `Bash command failed`, code 2, sans explication exploitable dans le log Airflow.

**Diagnostic :** l'utilisateur du conteneur était `uid=50000`, alors que le dossier
`/opt/airflow/dbt` appartenait à root et n'était pas accessible en écriture ; les
sous-dossiers `logs` et `target` étaient absents. L'alignement des versions dbt
avait été vérifié, mais n'avait pas suffi à résoudre cet incident.

**Contrôles non destructifs, sur le VPS :**

```bash
docker compose exec -T airflow id
docker compose exec -T airflow ls -ld /opt/airflow/dbt /opt/airflow/dbt/logs /opt/airflow/dbt/target
docker compose exec -T airflow dbt --version
```

**Correction :** rendre les répertoires de sortie accessibles à l'utilisateur effectif
d'Airflow, ou configurer des chemins de logs/artefacts inscriptibles. Déterminer les
chemins montés et leurs propriétaires avant de modifier les permissions.

**Prévention :** vérifier l'écriture après déploiement et garder les dépendances dbt
cohérentes. Ne pas appliquer `chmod -R 777` ou un changement de propriétaire global
sur le projet pour corriger deux dossiers.

**Validation :** exécution dbt réussie, tests de qualité passants et tables Gold actualisées.
**Statut connu :** fonctionnement confirmé par l'utilisateur après correction des permissions.

## INC-02 — Aucun DAG visible dans Airflow

**Symptôme observé :** fichiers présents dans `airflow/dags`, mais liste des DAG vide.
La vérification du `DagProcessorJob` retournait `No alive jobs found`.

**Investigation :** contrôler le montage, le chemin configuré et l'activité du DAG processor.

```bash
docker compose exec -T airflow airflow config get-value core dags_folder
docker compose exec -T airflow ls -la /opt/airflow/dags
docker compose exec -T airflow airflow jobs check --job-type DagProcessorJob --local
docker compose exec -T airflow airflow dags list-import-errors
docker compose logs --tail=150 airflow
```

**Actions selon le résultat :** corriger le montage si les fichiers sont absents ;
corriger les imports s'ils échouent ; rétablir le démarrage du processor ou ses permissions
si son traitement ne fonctionne pas. Un lancement manuel au terminal n'est pas une
solution durable au démarrage des processus.

**Prévention :** vérifier le processor après redémarrage, surveiller son heartbeat
et les erreurs d'import dans Grafana.
**Statut connu :** visibilité des DAG confirmée rétablie ; conserver les logs de la
correction précise si cet incident est présenté comme preuve à l'oral.

## INC-03 — Logs Airflow indisponibles : hostname du worker absent

**Message observé :** `Could not read served logs: Hostname not available for worker`.

**Nature :** échec de récupération des logs. Ce message seul ne prouve pas un problème
de configuration `hostname_callable` ni la cause de l'échec métier.

**Investigation :** identifier le run et la tâche exacts, vérifier leur état (en attente,
en cours, échoué), les heartbeats, les logs du scheduler et les montages des logs.

**Actions :** si la tâche n'a pas démarré, rechercher pourquoi elle reste en attente ;
si elle a démarré, vérifier le hostname enregistré et l'accès au serveur/fichiers de logs.
Ne pas modifier le hostname à l'aveugle ni effacer les traces pour masquer le symptôme.

**Prévention :** conserver les logs persistants et vérifier l'accès aux logs après déploiement.
**Statut connu :** symptôme signalé ; cause et résolution définitives non établies dans ce registre.

## INC-04 — Leaguepedia refuse les requêtes : `ratelimited`

**Symptôme observé :** échec de l'ingestion annuelle avec `APIError: ratelimited`.
La réponse fournie pour le compte indiquait `cargo-query: 60 hits / 60 seconds` ;
il ne s'agit pas d'un quota mensuel ni d'une garantie pour toute session d'authentification.

**Cause probable :** cadence de requêtes excessive, aggravée par des collectes concurrentes.

**Corrections présentes :** ingestion planifiée regroupée, espacement des requêtes Cargo,
attente croissante en cas de limitation et suivi des fenêtres déjà collectées.

**Prévention :** éviter de lancer plusieurs collecteurs indépendants avec le même compte,
ne pas relancer en boucle pendant la période de limitation et contrôler la couverture.
Le verrou de cadence du client est local au processus : il ne coordonne pas plusieurs machines.

**Validation :** reprise sans limitation persistante, nouvelles données chargées et progression
du rattrapage vérifiée. Un run partiel n'est pas une preuve de collecte exhaustive.
**Statut connu :** protections présentes dans le code ; absence durable de récidive à vérifier.

## INC-05 — Échec du téléchargement de l'image MinIO

**Symptôme observé :** `pull access denied for minio/minio`, puis téléchargements des
autres images interrompus ou messages `No such image`.

**Investigation :** isoler la première erreur ; vérifier registre, tag et accès réseau.
Une interruption du téléchargement de PostgreSQL ne prouve pas que son image est invalide.

**Correction présente :** références MinIO et client `mc` utilisant `quay.io` dans Compose.
**Prévention :** conserver des versions explicites et vérifier l'accès aux images avant maintenance.
**Statut connu :** commandes de téléchargement ensuite signalées fonctionnelles ; ne pas
attribuer la cause initiale à une suppression du dépôt sans preuve.

## INC-06 — Déploiement SSH refusé ou accès Git insuffisant

**Symptômes rencontrés :**

- mot de passe GitHub refusé pour les opérations Git HTTPS ;
- `Host key verification failed` dans GitHub Actions ;
- `Permission denied (publickey)` depuis le VPS ;
- clé de déploiement GitHub en lecture seule lors d'un `git push`.

**Diagnostic :** distinguer deux connexions indépendantes : GitHub Actions → VPS et
VPS → dépôt GitHub. Elles n'ont pas nécessairement le même utilisateur ni la même clé.

**Actions :** configurer la clé publique dans le bon `authorized_keys` pour le VPS ;
vérifier l'empreinte de l'hôte par une voie fiable avant de renseigner `VPS_KNOWN_HOSTS` ;
vérifier la clé utilisée pour GitHub et ses droits. Une clé de dépôt en lecture seule
permet un pull mais pas un push : effectuer les contributions depuis le poste autorisé.

**Prévention :** ne pas désactiver la vérification stricte de l'hôte ; ne pas copier les
clés privées dans le dépôt ; tester les deux connexions sous l'utilisateur effectif de la CI.
**Validation :** accès non interactif au VPS et lecture du dépôt réussis, puis déploiement testé.
**Statut connu :** plusieurs incidents distincts signalés ; vérifier chaque liaison séparément.

## INC-07 — Droits Git et Docker différents entre root et ubuntu

**Symptômes observés :** `dubious ownership`, écriture refusée dans le projet et `.git`,
ou accès refusé à `/var/run/docker.sock`.

**Diagnostic :** dépôt appartenant à root mais exploité par ubuntu. L'appartenance à
`docker` figurait dans `getent group docker`, mais pas encore dans `id` de la session.

```bash
whoami
id
getent group docker
ls -ld /home/ubuntu/MyLeague /home/ubuntu/MyLeague/.git
ls -l /var/run/docker.sock
```

**Actions :** choisir un utilisateur d'exploitation cohérent ; ajuster uniquement les droits
nécessaires en préservant ceux des répertoires montés dans les conteneurs. Ouvrir une nouvelle
session après un changement de groupes.

**Prévention :** `safe.directory` autorise la confiance Git, mais ne donne pas de droits
d'écriture. Un test réussi sous root ne prouve pas que la CI exécutée sous ubuntu fonctionnera.
Ne pas rendre le socket Docker accessible à tous : le groupe Docker confère des pouvoirs élevés.
**Statut connu :** origine des refus identifiée ; contrôles à refaire avec l'utilisateur de déploiement.

## INC-08 — Modifications de la webapp seulement partiellement visibles

**Symptôme observé :** certains filtres présents, mais anciens écrans d'entraînement ou
indicateurs/doublons encore visibles.

**Scénarios à distinguer :**

| Diagnostic | Action ciblée |
|---|---|
| Mauvais commit ou mauvaise image web | Vérifier le commit, reconstruire et recréer le service web |
| Mauvais port/tunnel ou ancienne page | Vérifier l'URL, le repère de version et recharger la page |
| Code à jour mais tables Gold anciennes | Exécuter les traitements dbt concernés sans chevauchement |
| Plans enregistrés indisponibles | Vérifier le démarrage de riot-live et l'initialisation du schéma `app` |

**Prévention :** utiliser la procédure [WEBAPP_UPDATE.md](WEBAPP_UPDATE.md). Le repère
`training-plans-matchups-v2` identifie une version fonctionnelle, pas un SHA Git exact.
Le script CD reconstruit les images mais ne reconstruit pas automatiquement les tables dbt.

**Validation :** vérifier un parcours utilisateur et les résultats SQL attendus, pas seulement `/healthz`.
**Statut connu :** modifications locales et tests documentés ; la version effectivement servie
sur le VPS doit être vérifiée à chaque déploiement.

## INC-09 — Joueur professionnel affiché en double

**Exemple observé :** `BrokenBlade` avec 123 parties et `BrokenBIade` (I majuscule)
avec 5 parties chez G2 en 2026. Des variantes de première lettre étaient aussi présentes.

**Investigation :** comparer les identifiants sources, l'équipe, la période et les participations,
plutôt que fusionner uniquement selon le pseudo affiché. Des homonymes réels existent.

**Correction présente :** normalisation limitée de la première lettre et correspondance
explicite `BrokenBIade` → `BrokenBlade`, limitée à G2 en 2026. Déduplication au grain
partie/joueur lors de la reconstruction Gold ; données brutes conservées.

**Validation réalisée :** requête de contrôle en lecture seule donnant une ligne de 128 parties,
et test de non-régression conservant les homonymes séparés.
**Prévention :** documenter chaque correspondance et éviter les rapprochements flous automatiques.
La correspondance BrokenBlade reste une correction ciblée fondée sur le contexte observé.
**Statut connu :** correction testée localement ; nécessite un nouveau build Gold sur le VPS.

## INC-10 — CI interrompue par une dépendance manquante

**Symptôme observé :** `ModuleNotFoundError: No module named 'matplotlib'` lors de
la collecte des tests Python : les tests n'avaient pas encore pu s'exécuter.

**Investigation :** identifier l'import et comparer les dépendances du poste local avec celles
installées dans GitHub Actions. Les avertissements de dépréciation ne sont pas cette erreur bloquante.

**Action :** déclarer la dépendance nécessaire dans l'ensemble installé par la CI,
ou isoler un import réellement optionnel sans désactiver le test concerné.
**Prévention :** installer depuis les fichiers de dépendances dans un environnement propre.
**Validation :** collecte des tests puis suite concernée réussies ; conserver le rapport CI.
**Statut connu :** incident constaté ; utiliser le dernier rapport CI comme preuve de résolution.

## INC-11 — Le DAG Spark remonte seulement une erreur HTTP 500

**Nature :** le runner a renvoyé une erreur ; le message Airflow ne donne pas la cause Spark.

```bash
docker compose --profile spark ps -a
docker compose logs --since=30m --tail=200 spark-runner spark-worker-1 spark-worker-2
```

**Actions selon les logs :** vérifier les workers, la résolution réseau du driver,
les dépendances/JAR requis, les ressources disponibles et la présence de la table
`gold.fact_match_participant`. Ne pas télécharger des JAR supplémentaires sans identifier
la classe ou le composant manquant.

**Prévention :** exécuter le test synthétique documenté dans
[services/spark/README.md](services/spark/README.md), puis contrôler un calcul réel.
**Validation :** exécution terminée, activité sur les deux executors et publication du résultat Gold.
**Statut connu :** erreur signalée ; cause exacte non établie ici à partir du seul HTTP 500.

## Avant de clôturer un incident

- [ ] Cause identifiée, ou incertitude explicitement documentée.
- [ ] Correction, opérateur, date et commit consignés.
- [ ] Résultat métier et couverture des données contrôlés.
- [ ] Rapport/log/capture conservé sans secrets.
- [ ] Communication de rétablissement effectuée si des utilisateurs ont été impactés.
- [ ] Action préventive ajoutée au code, à la CI ou à la feuille de maintenance.

Ne jamais utiliser `docker compose down -v` sur la production pour dépanner : cela
peut supprimer les volumes de données. Un redémarrage réussi n'est pas une restauration.

Documents complémentaires : [CI/CD](CI_CD.md), [supervision](MONITORING.md),
[plans d'entraînement](TRAINING_PLANS.md), [mise à jour webapp](WEBAPP_UPDATE.md).
