# Comparaison de joueurs de compétition

Espace **Joueurs pro** dans l'application React. Annuaire de 20 joueurs par page,
ouvert sur l'année courante, permettant de comparer de 2 à 5 joueurs distincts.
Les filtres, notamment le rôle, restreignent aussi la liste des joueurs.
Recherche de pseudo, filtres communs : région de compétition, tournoi, rôle,
équipe, champion et patch source Leaguepedia. L'équipe correspond à celle représentée
lors de chaque match, pas forcément au roster actuel. Le filtre équipe restreint
l'annuaire, la comparaison et les historiques ; le réinitialiser restaure toutes
les équipes. Changer de filtre réinitialise la sélection des joueurs et la page.
Les matchs soloQ ne sont jamais joints.

Les valeurs disponibles (winrate, KDA, CS, or, dégâts, vision et pool de champions)
sont comparées sur les participations filtrées, avec les effectifs renseignés.
CS/min et dégâts aux champions/min sont affichés dans la comparaison pro,
l'historique par partie et la comparaison coaching. Ils utilisent les statistiques
finales divisées par la durée en minutes ; les moyennes sont des moyennes de ratios
par partie. Une durée ou des dégâts absents ne sont jamais remplacés par zéro.
Les calculs API utilisent les colonnes Gold déjà présentes : reconstruire `web`
suffit pour l'affichage ; les anciennes collectes incomplètes nécessitent une
relecture par `leaguepedia_ingestion`. Gold@15 et solo kills pro restent indisponibles.
Les moyennes ignorent les données manquantes ; zéro réel n'est pas remplacé par
une absence. Le KDA est un ratio de sommes sur les lignes complètes, NULL sans
mort. Les moyennes par minute sont des moyennes de ratios par match, uniquement
sur les matchs ayant une durée positive renseignée. Ce n'est pas une métrique de lane.

La région provient de `Tournaments.Region`, pas du pays du joueur ou de son équipe
actuelle. Sans correspondance : « Non renseignée ». Le pseudo vient de `Players.ID`
quand la fiche correspond, sinon du Link observé ; les anciens alias ne sont pas
encore consolidés via PlayerRedirects. Deux alias peuvent donc diviser l'historique.
La présence dans une compétition Leaguepedia ne prouve pas un contrat professionnel.

## Items, runes et Gold@15

Le collecteur demande maintenant `Items`, `Trinket`, `KeystoneRune`, `PrimaryTree`,
`SecondaryTree`, `Runes`, `DamageToChampions` et `VisionScore` ; la durée numérique
est récupérée côté parties. JSON bronze et raw conservés ; les nouveaux champs
typés sont ajoutés à `gold.gold_pro_player_games` par dbt.

L'historique affiche les 20 dernières participations de chaque joueur sélectionné,
avec champion, équipe, compétition, résultat et détails items/runes quand présents.
Les icônes des objets et runes sont affichées lorsque leur correspondance est connue,
sinon le texte source est conservé.
Les objets correspondent au scoreboard final, pas à un ordre d'achat.

**Gold@15 et différence d'or à 15 minutes restent indisponibles** : aucun champ
correspondant n'a été confirmé dans ces scoreboards. L'écran le signale explicitement,
sans filtre numérique fictif et sans substituer l'or final. Une nouvelle source
de données compétitives à 15 minutes doit être validée avant d'activer cet indicateur.

Déclarations de champs utilisées :
- [ScoreboardPlayers](https://lol.fandom.com/wiki/Module:CargoDeclare/ScoreboardPlayers)
- [ScoreboardGames](https://lol.fandom.com/wiki/Module:CargoDeclare/ScoreboardGames)

## Déploiement

Draft Pro : filtres patch normalisé, région du tournoi et rôle observé.
Le modèle `gold_pro_draft_events` (tag `leaguepedia_active`) associe les picks aux
rôles des scoreboards par partie/équipe/champion. Un rôle absent ou ambigu ne sera
pas attribué. Les bans n'ont pas de rôle : leur affichage et la présence pick/ban
sont masqués lorsqu'un rôle est choisi ; la fréquence de pick au rôle est calculée
sur les parties avec événements de draft collectés pour ce patch et cette région.
Pour cette évolution, exécuter `leaguepedia_ingestion` jusqu'au build Gold avant
d'utiliser la nouvelle vue, puis reconstruire `web`.

1. Push/merge selon le workflow existant, puis déploiement de `web` et redémarrage Airflow.
2. Exécuter `leaguepedia_ingestion` : historique, référentiels, puis build Gold.
3. Actualiser le site et ouvrir **Joueurs pro**.

Le nouveau backend nécessite le nouveau build Gold : tant qu'il n'a pas abouti,
la page peut afficher une erreur de données indisponibles. Pour reconstruire depuis
les données raw existantes sans attendre une nouvelle collecte :

```bash
docker compose exec -T airflow dbt build --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt/profiles --select tag:leaguepedia_active --indirect-selection cautious --target-path /tmp/dbt-leaguepedia-active/target --log-path /tmp/dbt-leaguepedia-active/logs
```

Ne pas lancer ce build en même temps que le DAG Leaguepedia. Aucun nouveau secret,
aucune suppression ni réinitialisation de raw. Les anciens snapshots sans items/
runes/durée resteront incomplets jusqu'à leur relecture progressive par le DAG.
Le rythme Cargo de 2 secondes et le backoff existants restent appliqués.

Tests unitaires des endpoints/filtres et des champs Cargo ; test d'intégration
étendu dans `tests/integration/test_leaguepedia_active.py` (PostgreSQL/MinIO/dbt réels,
réponses externes simulées). L'API publique n'a pas été appelée avec les secrets du projet.
