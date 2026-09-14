# Plans d’entraînement

Coaching conserve le diagnostic, l’historique, les comparaisons et les analyses collectives.
Entraînement contient désormais les objectifs enregistrés, les bilans de séance,
le pool joué et les match-ups à travailler. Le diagnostic de lane n’y est plus dupliqué.

Les objectifs sont stockés dans `app.training_goals`, les séances dans
`app.training_sessions` (PostgreSQL Gold). Leur initialisation additive se fait au
démarrage de riot-live. Les données sources et les tables existantes ne sont pas supprimées.
Le compte SQL du web reste en lecture seule : les opérations passent par le service interne.
Le backend Docker copie uniquement le module de validation/stockage requis, sans secrets.

Accès privé partagé par le staff, comme le roster existant : ce n’est pas un système
multi-utilisateur avec authentification ou isolation entre clubs. Ne pas exposer publiquement.
Les joueurs doivent être dans le roster pour accéder à leur plan. Les retirer ne supprime
pas leurs objectifs ; les réajouter rend les plans accessibles à nouveau.

La période est en UTC, fin incluse, 366 jours maximum, tous patches confondus.
Les mesures proviennent de `gold.gold_player_lane`, sans limite aux 200 derniers matchs.
Les filtres champion/rôle sont ceux de l’objectif ; le patch global ne le filtre pas.
Le seuil est un minimum, sauf les morts sans assist avant 15 minutes (maximum).
Les valeurs absentes ne sont ni des zéros ni des succès. Les taux affichent leur effectif.
Les statuts sont choisis par le coach, les statistiques sont recalculées avec les données
disponibles, y compris après clôture (pas de photographie historique figée).

Les moyennes GD@15/XPD@15 du pool joué sont calculées par champion/rôle/patch sur
les valeurs disponibles, avec leur nombre de parties renseignées. Elles utilisent
une jointure par match et PUUID ; pas de moyenne des moyennes ni d’imputation à zéro.

## Déploiement après push/pull

```bash
docker compose up -d --build riot-live web
```

`gold_player_lane` doit exister et être à jour (`dbt_transform`). Le prochain passage
de collecte puis dbt actualisera les mesures des plans. Aucun nouveau DAG n’est nécessaire.
Inclure le schéma `app` dans les sauvegardes ; le dump complet Gold existant le couvre.
