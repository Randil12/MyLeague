# MyLeague — Plateforme data d'analyse de la méta League of Legends

Projet de fin d'études (RNCP 39586 — Ingénieur en science des données).

**Commanditaire (fictif)** : Nexus Esport Academy, structure e-sport accompagnant joueurs et équipes dans leur progression.

**Problématique** : comment une structure e-sport peut-elle transformer des données de jeu massives, hétérogènes et en évolution constante (un patch toutes les deux semaines) en analyses fiables de la méta, afin d'éclairer ses décisions de draft, d'entraînement et de coaching ?

## Architecture

```mermaid
flowchart TB
    SRC["SOURCES EXTERNES<br/>Riot API — Data Dragon — Leaguepedia — Notes de patch"]
    AF["APACHE AIRFLOW<br/>7 pipelines planifiés (détail ci-dessous)"]
    MINIO["MINIO — DATA LAKE<br/>Zone bronze : JSON bruts partitionnés, source de vérité"]
    WH["POSTGRESQL — ENTREPÔT<br/>Schémas raw + reference : données chargées"]
    GOLD["POSTGRESQL — GOLD<br/>Tables d'analyse : méta, presence, builds, méta pro"]
    VIZ["RESTITUTION — lecture seule (rôle data_analyst)<br/>Grafana (dashboards) — Streamlit (application coachs)"]
    AUD["AUDIT<br/>Traçabilité de<br/>chaque exécution"]

    SRC -->|"collecte : API, SQL, scraping"| AF
    AF -->|"archivage brut"| MINIO
    MINIO -->|"chargement JSONB"| WH
    WH -->|"transformation dbt<br/>(staging → intermediate → gold)"| GOLD
    GOLD -->|"lecture seule"| VIZ
    AF -.->|"journalise"| AUD
    AUD -.->|"supervision"| VIZ
```

### Les 7 pipelines Airflow

| DAG | Rôle | Pattern | Fréquence |
|---|---|---|---|
| `datadragon_ingestion` | Référentiel du jeu (champions, objets, runes) | ETL | Quotidien |
| `riot_euw_ingestion` | Matchs classés + timelines EUW | ELT (E/L) | Quotidien |
| `leaguepedia_ingestion` | Tournois, équipes, parties professionnelles | ELT (E/L) | Quotidien |
| `patch_notes_scraping` | Notes de patch officielles | Scraping | Quotidien (à chaque nouveau patch) |
| `riot_live_spectator` | Parties en cours des joueurs suivis | Micro-batch temps réel | Toutes les 30 min |
| `riot_academy_tracking` | Maîtrises des joueurs du club | ELT | Quotidien |
| `dbt_transform` | Construction des tables d'analyse + tests qualité | ELT (T) | Quotidien |

Architecture en médaillon : **bronze** (JSON bruts dans MinIO, unique zone bronze — écriture locale seulement en mode dégradé sans MinIO), **raw/reference** (warehouse Postgres), **staging → intermediate → gold** (modèles dbt), **audit** (traçabilité des runs). Devise : *MinIO conserve, Postgres calcule.*

## Deux patterns d'intégration assumés

| Source | Pattern | Pourquoi |
|---|---|---|
| Riot API (matchs) | **ELT** | Volumineux, schéma évolutif à chaque patch. JSON brut chargé en JSONB, transformation SQL déléguée à dbt : on peut retraiter tout l'historique sans re-solliciter l'API (rate limits). |
| Data Dragon | **ETL** | Petit référentiel stable. Transformation en Python (typage, aplatissement) avant chargement dans `reference.dim_*`, versionné par patch. |
| Leaguepedia | ELT | Données e-sport pro (tournois, équipes, picks/bans par patch) via l'API Cargo. Permet la comparaison méta pro vs solo queue. |
| CSV internes | ETL | Validation/nettoyage indispensables avant chargement. *(à venir)* |

```mermaid
flowchart TB
    subgraph ETL["FLUX ETL — Data Dragon (référentiel : faible volume, schéma stable)"]
        direction LR
        E1["1 — EXTRACT<br/>API Data Dragon<br/>JSON champions, objets,<br/>sorts, runes"]
        E2["2 — TRANSFORM<br/>Python : typage,<br/>aplatissement, extraction<br/>de colonnes"]
        E3["3 — LOAD<br/>reference.dim_champion<br/>dim_item, dim_rune,<br/>dim_summoner_spell"]
        E1 --> E2 --> E3
    end

    subgraph ELT["FLUX ELT — Riot & Leaguepedia (volumineux : schéma évolutif à chaque patch)"]
        direction LR
        L1["1 — EXTRACT<br/>API Riot match-v5<br/>JSON matchs, timelines"]
        L2["2 — LOAD<br/>bronze MinIO puis<br/>raw.riot_matches<br/>(JSONB brut, tel quel)"]
        L3["3 — TRANSFORM<br/>dbt (SQL) : staging →<br/>intermediate → gold<br/>+ tests de qualité"]
        L1 --> L2 --> L3
    end

    ETL ~~~ ELT
```

La différence tient à la place du T : en **ETL**, la donnée est transformée *avant* d'entrer dans l'entrepôt (adapté à un référentiel stable et léger) ; en **ELT**, la donnée brute entre d'abord, et la transformation SQL se rejoue à volonté sur tout l'historique sans rappeler l'API (décisif sous contrainte de quotas).

## Composants

| Service | Rôle | Accès local |
|---|---|---|
| Airflow 3 | Orchestration des pipelines | http://localhost:8080 |
| MinIO | Data lake (bronze) | http://localhost:9001 |
| Postgres `gold` | Warehouse analytique | localhost:5433 |
| dbt | Transformations SQL + tests de qualité | conteneur `myleague-dbt` |
| Grafana | Dashboards méta + supervision | http://localhost:3000 |
| Streamlit | Application web métier (coachs) | http://localhost:8501 |

## Démarrage rapide

```bash
# 1. Configurer les secrets (jamais commités)
cp .env.example .env   # renseigner RIOT_API_KEY

# 2. Lancer la stack
docker compose up -d

# 3. Déclencher les DAGs dans Airflow (localhost:8080)
#    datadragon_ingestion  -> ETL référentiel
#    riot_euw_ingestion    -> ELT matchs Master+ EUW
#    dbt_transform         -> modèles staging/intermediate/gold + tests dbt

# 4. Consulter les dashboards Grafana (localhost:3000)
```

## Développement

```bash
pip install -r requirements-dev.txt
ruff check jobs tests      # lint
pytest                     # tests unitaires
```

La CI GitHub Actions (`.github/workflows/ci.yml`) exécute lint, tests unitaires et validation du projet dbt à chaque push/PR.

## Structure du dépôt

```
airflow/dags/     DAGs Airflow (ingestion ETL/ELT, transformation dbt)
jobs/             Logique métier des pipelines (clients API, ingestion, load)
dbt/              Projet dbt (sources, staging, intermediate, gold, tests)
grafana/          Provisioning datasource + dashboards
postgres/         Schémas et tables d'initialisation du warehouse
data/             Zone bronze locale (non versionnée)
tests/            Tests unitaires (pytest)
```

## Données personnelles et sécurité

Les joueurs sont identifiés par leur `puuid` (identifiant pseudonymisé fourni par Riot) ; aucun nom réel n'est collecté ni stocké. Les secrets (clé API Riot, mots de passe) sont gérés par variables d'environnement via `.env`, exclu du versioning.

Principe du moindre privilège (`postgres/init_roles.sql`) : le rôle `data_engineer` a accès à tous les schémas data ; le rôle `data_analyst` est en lecture seule sur `gold`, `reference` et `audit` — c'est ce rôle qu'utilisent Grafana et l'application Streamlit, qui ne peuvent donc ni écrire ni accéder aux zones brutes. Le détail de la politique de sécurité est documenté dans `docs/` *(à venir, voir ROADMAP)*.

Voir [ROADMAP.md](ROADMAP.md) pour les étapes restantes vers la certification.
