# MyLeague — Draft, Entraînement, Coaching

`frontend/` : React + TypeScript + Vite. `backend/` : API FastAPI et SQL en lecture
seule. PostgreSQL, Airflow et dbt restent inchangés. Aucun dossier `webapp/`.

## Démarrer sur le PC avec les données du VPS

Prérequis : Node.js 24, Python et le `.env` racine existant. Les commandes sont
exécutées depuis la racine du dépôt. Le backend lit ce `.env`, mais les variables
du terminal sont prioritaires. Le frontend ne lit jamais les secrets PostgreSQL.

1. Terminal PowerShell pour le tunnel (le conserver ouvert) :

```powershell
ssh -N -L 127.0.0.1:15433:127.0.0.1:5433 root@IP_DU_VPS
```

Si ce tunnel est déjà ouvert pour DBeaver, ne pas le recréer.

2. Autre terminal PowerShell, backend :

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
$env:GOLD_POSTGRES_HOST = "127.0.0.1"
$env:GOLD_POSTGRES_PORT = "15433"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8511 --reload
```

Les valeurs `DATA_ANALYST_USER`, `DATA_ANALYST_PASSWORD` et `GOLD_POSTGRES_DB` du
`.env` local doivent correspondre à celles du VPS. Ne pas les copier dans un
fichier `VITE_*` : ces variables seraient intégrées au JavaScript public.

3. Troisième terminal PowerShell, frontend :

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Ouvrir **http://127.0.0.1:5173**. Vite transmet `/api` au backend sur `8511`.
Garder les trois terminaux ouverts ; `Ctrl+C` pour arrêter. Le port frontend
est strict : si 5173 est occupé, fermer l'ancien serveur plutôt que changer
silencieusement d'adresse. Sans base joignable, les écrans expliquent l'absence
de données et n'affichent aucun résultat inventé.

## Déployer sur le VPS

Après commit/push depuis le PC :

```bash
cd /home/ubuntu/MyLeague
git pull origin dev
docker compose --profile legacy stop streamlit
docker compose up -d --build web
docker compose ps web
```

Le Dockerfile compile React dans une étape Node, puis sert le frontend et l'API
avec FastAPI sur le même port. Node n'est pas nécessaire à l'exécution.
Le site remplace Streamlit sur le port privé VPS `8501`. L'ancien Streamlit reste
dans `app/`, activable avec le profil `legacy` sur le port privé `8502`.
Ne pas supprimer les volumes : aucune migration ni remise à zéro n'est nécessaire.

Depuis le PC :

```powershell
ssh -N -L 127.0.0.1:18501:127.0.0.1:8501 root@IP_DU_VPS
```

Ouvrir **http://127.0.0.1:18501**. Un tunnel existant vers le port VPS 8501 convient.

## Fonctionnalités et limites métier

| Fonction | Données et méthode | Limites |
|---|---|---|
| Priorités draft | Score existant `gold_draft_recommendations`, pick/ban, confiance | Pas de moteur de synergies ; exclusions uniquement dans l'onglet |
| Flex picks | Participant/champion/rôle, au moins deux rôles au-dessus du seuil | Rôles observés, pas une garantie de viabilité |
| Match-ups | Même match, équipes opposées, même rôle ; rôles ambigus exclus | Winrate final, écarts finaux, pas des statistiques de lane à 15 min |
| Compositions | Cinq participants et cinq rôles distincts, composition exacte | Petits échantillons fréquents ; pas d'effet causal démontré |
| Plan Academy | Maîtrise et score dbt | Dernier patch, joueurs Academy et champions avec ≥ 100 picks uniquement |
| Difficultés individuelles | Match-ups du joueur avec ≥ 3 occurrences, tri winrate | Signal exploratoire à confirmer en VOD |
| Coaching individuel | KDA agrégé, CS/min, historique et évolution par patch | Seulement les matchs collectés ; KDA inconnu si aucune mort |
| Coaching collectif | Exactement les cinq joueurs sélectionnés du même côté | Collecte solo queue : aucun match commun peut exister ; pas de scrims |
| Situations de jeu | Non implémenté | Nécessite des indicateurs issus des timelines, pas les seules statistiques finales |

Le roster liste au maximum 500 joueurs suivis, Academy en premier. Historique
individuel : 50 matchs/patch ; collectif : 100 matchs/patch ; évolution individuelle :
24 patches. Les match-ups sont limités à 300 lignes, compositions à 100.
Les exports CSV portent sur les lignes affichées, avec taux bruts entre 0 et 1.
Les requêtes dérivées lisent `gold.fact_match_participant` ; timeout de 10 secondes.
À grande volumétrie, matérialiser ces agrégats dans dbt avec les index adaptés.

## Sécurité

Accès privé par SSH, **pas de comptes web ni de séparation des droits coach/joueur**.
Tous les utilisateurs du tunnel ont accès aux mêmes vues. Ne pas ouvrir le port
sur Internet sans ajouter une authentification et HTTPS.

Rôle SQL `data_analyst`, transactions en lecture seule, paramètres SQL liés,
requêtes prédéfinies, erreurs expurgées, CSP, conteneur non-root et système de
fichiers en lecture seule. Aucune donnée brute ou clé Riot envoyée au navigateur.
Le healthcheck `/healthz` contrôle HTTP, pas la fraîcheur ni la connexion PostgreSQL.

## Vérifications ciblées

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_coaching_api.py -q
cd frontend
npm.cmd test
npm.cmd run build
```

Les tests de l'API utilisent des réponses simulées. Ils ne remplacent pas la
validation avec une vraie base après déploiement. Les tests existants des pipelines
ne sont pas modifiés ; la CI exécute aussi le build du frontend.
