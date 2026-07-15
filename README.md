# MyLeague — Plateforme data d'analyse de la méta League of Legends

Projet de fin d'études (RNCP 39586 — Ingénieur en science des données).

**Commanditaire (fictif)** : Nexus Esport Academy, structure e-sport accompagnant joueurs et équipes dans leur progression.

**Problématique** : comment une structure e-sport peut-elle transformer des données de jeu massives, hétérogènes et en évolution constante (un patch toutes les deux semaines) en analyses fiables de la méta, afin d'éclairer ses décisions de draft, d'entraînement et de coaching ?

## Architecture

```mermaid
flowchart TB
    SRC["SOURCES EXTERNES<br/>Riot API — Data Dragon — Leaguepedia — Notes de patch"]

    subgraph DOCKER["DOCKER COMPOSE — stack MyLeague"]
        AF["APACHE AIRFLOW<br/>Orchestration : 7 pipelines planifiés<br/>(ingestion, temps réel, transformation — détail ci-dessous)"]

        subgraph MED["ARCHITECTURE MÉDAILLON"]
            direction TB
            BRONZE[("BRONZE — MinIO (data lake)<br/>JSON bruts partitionnés, immuables<br/>source de vérité")]
            RAWREF[("RAW + REFERENCE — PostgreSQL<br/>JSONB chargé tel quel + référentiel typé")]
            STG[("STAGING / INTERMEDIATE — PostgreSQL<br/>vues dbt : typage, filtres, jointures")]
            GOLD[("GOLD — PostgreSQL<br/>tables d'analyse : méta, presence, builds, méta pro")]

            BRONZE -->|"chargement JSONB"| RAWREF
            RAWREF -->|"dbt"| STG
            STG -->|"dbt + tests qualité"| GOLD
        end

        AUD[("AUDIT — PostgreSQL<br/>traçabilité de chaque exécution")]
        GRAF["GRAFANA<br/>dashboards méta + supervision"]
        ST["STREAMLIT<br/>application coachs"]
    end

    SRC -->|"collecte : API, SQL, scraping"| AF
    AF -->|"archivage brut"| BRONZE
    AF -.->|"journalise"| AUD
    GOLD -->|"lecture seule"| GRAF
    GOLD -->|"lecture seule"| ST
    AUD -.->|"supervision"| GRAF
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
        L1["1 — EXTRACT<br/>API Riot, API Leaguepedia<br/>matchs, timelines, parties pro"]
        L2["2 — LOAD<br/>bronze MinIO puis<br/>raw.riot_* et raw.leaguepedia_*<br/>(JSONB brut, tel quel)"]
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

Principe du moindre privilège (`postgres/init_roles.sql`) : le rôle `data_engineer` a accès à tous les schémas data ; le rôle `data_analyst` est en lecture seule sur `gold`, `reference` et `audit` — c'est ce rôle qu'utilisent Grafana et l'application Streamlit, qui ne peuvent donc ni écrire ni accéder aux zones brutes.

### Architecture de sécurité — trois zones

```mermaid
flowchart TB
    COACH["👤 Coachs / analystes du club"]
    ENG["👤 Data engineer"]

    subgraph Z1["ZONE EXPOSITION — seuls points d'accès des utilisateurs métier"]
        GRAF["Grafana<br/>port exposé : 3000"]
        ST["Streamlit<br/>port exposé : 8501"]
    end

    subgraph Z2["ZONE TRAITEMENT — détient les secrets (.env)"]
        AF["Airflow<br/>port exposé : 8080 (équipe technique)"]
        DBT["dbt"]
    end

    subgraph Z3["ZONE DONNÉES — réseau interne Docker, jamais exposée aux utilisateurs"]
        PG[("PostgreSQL entrepôt<br/>port 5433 : dev uniquement,<br/>fermé en production")]
        MINIO[("MinIO — data lake<br/>ports 9000/9001 : dev uniquement,<br/>fermés en production")]
    end

    COACH -->|"HTTP :3000 / :8501"| GRAF
    COACH -->|"HTTP :8501"| ST
    ENG -->|"admin Airflow :8080"| AF
    ENG -->|"compte data_engineer<br/>(tous schémas data)"| PG

    GRAF -->|"compte data_analyst<br/>SELECT sur gold, reference, audit"| PG
    ST -->|"compte data_analyst<br/>lecture seule"| PG
    AF -->|"compte gold (technique)<br/>écriture raw, reference, audit"| PG
    DBT -->|"compte gold<br/>construit staging → gold"| PG
    AF -->|"clés d'accès S3"| MINIO
```

En développement local, les ports de la zone données (5433, 9000/9001) sont publiés pour faciliter le travail (DBeaver, console MinIO) ; la cible de production les ferme et ajoute TLS sur les interfaces exposées via un reverse proxy. Le détail de la politique de sécurité est documenté dans `docs/` *(à venir, voir ROADMAP)*.

Voir [ROADMAP.md](ROADMAP.md) pour les étapes restantes vers la certification.
