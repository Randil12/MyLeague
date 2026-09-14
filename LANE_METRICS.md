# Indicateurs de lane et objectifs de séance

Disponibles dans Entraînement et Coaching individuel, uniquement pour les joueurs
du roster. Source : matchs et timelines Riot stockés, pas les scoreboards pro.

## Calculs

- `damage_min` : dégâts totaux aux champions × 60 / durée en secondes.
- `cs_min` : CS totaux (sbires + monstres) × 60 / durée en secondes.
  Ces deux indicateurs portent sur la partie entière, sans dépendre des timelines.
  Durée absente/non positive ou valeur source absente : NULL. Les cartes affichent
  la moyenne des ratios par partie renseignée, pas le ratio des sommes.

- `solo_kills` : valeur Riot `challenges.soloKills`, NULL si absente.
- `gold_15`, `cs_15`, `xp_15` : `totalGold`, `minionsKilled + jungleMinionsKilled`,
  `xp` de l'observation la plus proche de 900 000 ms, tolérance de 5 000 ms.
  En cas d'égalité on prend l'observation la plus ancienne. L'heure réelle est conservée.
- `gd_15`, `csd_15`, `xpd_15` : joueur moins adversaire dans l'équipe opposée au
  même rôle déclaré ; il faut un seul participant à ce rôle dans chaque équipe.
  Ce n'est pas une détection géographique des lanes : les lane swaps restent une limite.
- `solo_kills_15`, `solo_deaths_15` : événements CHAMPION_KILL strictement avant
  900 000 ms, sans assistance enregistrée (liste vide ou omise par Riot), tueur
  joueur non nul. Les événements JSON identiques sont dédupliqués ; les exécutions
  sont exclues. Ce n'est pas la preuve d'un duel isolé, ni forcément la même
  définition que le compteur Riot `challenges.soloKills`.
- La timeline doit couvrir le début (<=1 s) jusqu'à 15 minutes, avec tableaux
  d'événements présents et sans intervalle de plus de 90 s avant 15 minutes.
  Cette vérification détecte les trous de frames, pas tous les événements omis par la source.
- Partie de moins de 900 s : toutes les mesures à 15 minutes sont NULL.
  Un manque de données n'est jamais remplacé par zéro.

## Application

Le modèle `gold.gold_player_lane` est reconstruit par `dbt_transform`. L'API
`/api/lane` croise le roster courant et limite les résultats aux 200 dernières
parties d'un joueur sur le patch choisi. Les filtres rôle, champion et date UTC
s'appliquent à cet échantillon. Chaque moyenne affiche son effectif renseigné.

La fréquence d'avance est la proportion de GD@15 strictement positifs parmi les
parties où GD@15 est connu. La conversion affichée est le winrate sur ces parties
en avance : ce n'est ni un effet causal, ni la conservation de l'avance à 20 minutes.

L'objectif de séance permet de choisir une métrique et un minimum ou maximum.
Le seuil est inclus ; la réussite est évaluée partie par partie et les valeurs
inconnues sont exclues du dénominateur. **Le réglage est temporaire, non enregistré** :
aucune table d'objectifs persistants, aucun historique de décisions du coach dans
cette version. Changer de joueur ou de patch réinitialise le réglage.

## Déploiement et vérification

Après push/pull, redémarrer Airflow, exécuter `dbt_transform` et reconstruire `web`.
Si des matchs/timelines manquent, lancer `riot_coach_matches` (50 parties récentes
maximum par joueur) ou le backfill historique. Aucun nouvel appel Riot pour
recalculer les métriques d'une timeline déjà stockée. Ne pas lancer un build dbt
manuel en parallèle du DAG existant sur les mêmes modèles.

Tests : API avec paramètres liés et restriction au roster ; calculs d'objectifs
frontend ; SQL réel via fixtures SELECT uniquement (valeurs exactes, absence,
partie courte, tolérance, doublons, exécutions, rôles ambigus, trous de timeline).
