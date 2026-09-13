# CI/CD GitHub Actions

## Ce qui est automatisé

Le workflow **CI** s'exécute sur les pushes vers `dev` et `main`, les pull requests
et les lancements manuels. Aucun secret de production n'est nécessaire aux tests.

| Contrôle | Couverture |
|---|---|
| Python | Ruff et tests unitaires existants |
| Frontend | npm ci, tests Node, vérification TypeScript et build Vite |
| Configuration | Compose production avec `.env.example`, Compose CI, syntaxe Bash |
| Intégration dbt | PostgreSQL 15 réel, schémas réels, deux matchs fictifs (20 participants), `dbt build --select +fact_match_participant` avec ses tests |
| Intégration live | Ajout via FastAPI → HTTP interne du roster → PostgreSQL → collecte → vrai MinIO → lecture API → retrait ; déduplication et absence de fuite PUUID/clé observateur |
| Droits | Le compte lecture seule ne peut pas supprimer les données Gold |
| Intégration Spark | Lanceur HTTP réel, master + deux workers, job JDBC réel, vérification des dix match-ups publiés et de l'audit |
| Images | Construction des images web, riot-live et Spark (une seule fois pour Spark) |

Les seuls services simulés sont les réponses externes Riot (identité et partie).
La CI ne consomme pas tes quotas et ne prétend pas valider ta clé API réelle.
Elle ne teste pas tous les modèles dbt, l'import réel d'Airflow 3.2, Leaguepedia
en ligne ou le navigateur : ces limites sont distinctes des tests d'intégration.
Le job Spark exige deux executors enregistrés ; les valeurs publiées sont testées.
Pour prouver la répartition précise des tâches, conserver aussi la preuve Executors
décrite dans `services/spark/README.md`.

`compose.ci.yml` utilise le projet Docker **myleague-ci**, des données éphémères en
tmpfs et des ports locaux dédiés (25432, 29000, 28090). Ne jamais remplacer ce fichier
par `docker-compose.yml` pour lancer/nettoyer les tests. Les identifiants `ci-*`
sont publics et réservés aux conteneurs de test, pas à la production.

Les rapports JUnit et logs des conteneurs sont téléchargeables dans **Actions → CI
→ Artifacts**, conservés sept jours, y compris après échec. Les dépendances doivent
pouvoir être téléchargées depuis les registres ; une panne de registre peut faire
échouer la construction avant les tests.

## Activer dans GitHub

1. Commit/push ces fichiers sur `dev` ; ouvrir **Actions → CI** pour suivre le run.
2. Pour une pull request, tous les contrôles doivent être verts avant fusion.
3. Configurer les règles de protection de `main`/`dev` pour exiger les jobs CI,
   frontend, configuration et intégration. Le dépôt doit d'abord avoir reçu un run
   pour que GitHub propose leurs noms.
4. Les fichiers de workflow doivent aussi être présents sur la branche par défaut
   pour que le bouton **Run workflow** soit disponible.

## CD : configuration initiale (une fois)

Le déploiement est **manuel après tous les tests**, pas automatique sur push.
Créer l'environnement GitHub **production** dans Settings → Environments. Ajouter
un reviewer obligatoire et limiter les branches à `dev`/`main` si ces protections
sont disponibles pour le type de dépôt et l'abonnement GitHub.

Ajouter ces secrets **dans cet environnement** :

| Secret | Valeur |
|---|---|
| `VPS_HOST` | Adresse IPv4 ou nom DNS du VPS (sans `ssh`, utilisateur ou protocole) |
| `VPS_USER` | Utilisateur de déploiement, par exemple `ubuntu` |
| `VPS_PORT` | Port SSH ; optionnel, 22 par défaut |
| `VPS_SSH_KEY` | Clé privée SSH dédiée à GitHub Actions, sans passphrase ; jamais dans Git ni dans ce chat |
| `VPS_KNOWN_HOSTS` | Entrée known_hosts du VPS vérifiée via une connexion de confiance ; avec `[hôte]:port` pour un port non standard |

Installer la clé **publique** correspondante dans `authorized_keys` de l'utilisateur
VPS. Cette connexion GitHub Actions → VPS est distincte de la connexion VPS → GitHub
déjà utilisée pour `git pull`. L'utilisateur VPS doit pouvoir lire le dépôt privé
sans saisie interactive, gérer Docker et écrire dans `/home/ubuntu/MyLeague`.
Attention : l'accès au groupe Docker confère des privilèges comparables à root.
Ne pas utiliser de runner auto-hébergé sur le VPS pour exécuter les pull requests.

Vérifier l'empreinte SSH hors bande avant d'enregistrer `VPS_KNOWN_HOSTS` ; le workflow
ne fait pas un `ssh-keyscan` aveugle et ne désactive pas la vérification d'hôte.
Ne copier ni `.env`, ni la clé Riot, ni les mots de passe de la base dans les secrets
CI : ils restent sur le VPS et sont utilisés par Compose lors du déploiement.

Préconditions du VPS : infrastructure PostgreSQL/MinIO initialisée et démarrée,
`.env` présent, worktree sans modifications suivies, ressources suffisantes pour
Spark et aucun job Airflow/Spark en cours à interrompre. Le chemin du projet est
fixé explicitement dans `scripts/deploy-vps.sh` ; adapter ce fichier si nécessaire.
Ne pas exposer PostgreSQL, MinIO ou Spark à Internet pour la CI.

## Lancer un déploiement

Actions → **CI → Run workflow** → choisir `dev` (ou `main`) → cocher **deploy**.
Les tests s'exécutent sur le commit choisi. Si tous passent, le job `deploy` attend
l'approbation de l'environnement lorsqu'elle est configurée, puis :

1. Connexion SSH avec vérification d'hôte.
2. Avance le dépôt VPS en fast-forward vers le **SHA testé**, sans reset forcé.
   Si le VPS est divergent ou déjà au-delà du SHA demandé, l'opération échoue.
3. Construit web, riot-live et l'image Spark unique sur le VPS.
4. Met à jour ces conteneurs sans recréer les bases, puis redémarre Airflow.
5. Vérifie l'API web, l'accès à la liste de suivi et deux workers Spark ALIVE.

Ces sondes ne prouvent pas la validité de la clé Riot ou la réussite d'un DAG métier.
Le déploiement n'est pas sans interruption ; il recharge notamment les DAGs Airflow.
Les autres conteneurs (Grafana, MinIO, bases) ne sont pas mis à jour par cette CD.
Les images sont reconstruites depuis le SHA testé, pas promues par digest depuis
la CI ; une dépendance non figée peut donc changer entre les deux constructions.

Pas de rollback automatique. Le journal indique le SHA précédent. En cas d'échec,
inspecter les logs avant toute relance ; pour revenir sur une modification de code,
créer un commit de revert, le tester puis le déployer. Ne pas utiliser `down -v`
sur le VPS. Les migrations SQL et les données nécessitent une stratégie de sauvegarde
distincte ; le script n'efface ni volumes, ni `.env`.

## Rejouer les intégrations localement

Docker doit être démarré et les ports CI libres. Depuis PowerShell à la racine,
avec le venv actif et `requirements-dev.txt` installé :

```powershell
docker compose -f compose.ci.yml build spark-master
docker compose -f compose.ci.yml up -d --no-build --wait --wait-timeout 120
$env:RUN_INTEGRATION_TESTS = "1"
pytest tests/integration -v
Remove-Item Env:RUN_INTEGRATION_TESTS
docker compose -f compose.ci.yml down --volumes --remove-orphans
```

Le dernier ordre supprime **uniquement les données de la stack CI jetable**.
Les fixtures ciblent explicitement `127.0.0.1:25432/myleague_ci`, imposent les
identifiants CI et vérifient le nom de base avant les écritures. Ne pas faire de
tunnel vers une base distante sur ces ports de test. Sans le flag d'activation,
`pytest` ignore les tests d'intégration.

Références : [conteneurs de service GitHub Actions](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers),
[syntaxe et permissions des workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
