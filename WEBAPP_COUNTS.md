# Périmètre des compteurs et statistiques joueurs

## Diagnostic du 16 septembre 2026

Vérification PostgreSQL en lecture seule : `gold.gold_patch_summary` contient
3 380 matchs pour le patch 16.18 au moment du contrôle. Le compteur de la webapp
et celui du dashboard Grafana Méta lisent cette même table.
La webapp conservait sa réponse initiale jusqu'à actualisation manuelle ; un décalage
de rafraîchissement est donc possible. Les nombres constatés ne sont pas figés.
Le résumé est maintenant relu chaque minute lorsque la page est visible et au retour
du focus. Si un écart persiste après actualisation, comparer le patch exact, le serveur
PostgreSQL configuré et le panneau Grafana (audit brut et Gold ne sont pas équivalents).

Un joueur suivi avait 216 parties au total, dont seulement 7 sur le patch 16.18.
La sélection affichait un total tous patches, tandis que les statistiques utilisaient
le patch sélectionné : ce n'était pas la preuve de parties manquantes.

## Comportement actuel

- Entraînement et Coaching individuel proposent **Tous les patches** par défaut.
- Changer de joueur ou d'écran réinitialise le filtre à tous les patches.
  Un filtre explicite ne s'applique qu'au joueur et à l'écran qui l'ont sélectionné.
- Vérification en lecture seule : Tacos38w a 48 lignes de statistiques, dont 37
  sur 16.17 et 11 sur 16.18. Parmi les 48, 47 ont un GD@15 renseigné.
  Le repère de version du frontend est `player-scope-v3`.
- Le nombre du sélecteur est explicitement un total ; le filtre patch détermine les analyses.
- Draft et Coaching collectif conservent leur filtre de patch obligatoire.
- Le diagnostic de lane n'est plus limité aux 200 dernières parties. Ses moyennes
  portent sur toutes les lignes disponibles pour le joueur et les filtres sélectionnés.
  L'affichage est paginé par 50 lignes côté navigateur, sans limiter les calculs.
- L'historique individuel est paginé côté serveur par 20 parties, sans limite
  aux 50 dernières. Joueur, patch ou actualisation réinitialisent la page.
  Les statistiques globales ne sont pas limitées à la page ; le CSV exporte la page.
- Les objectifs enregistrés gardent leur propre période UTC et leurs filtres,
  indépendamment du patch global. Ils ne sont pas censés couvrir tout l'historique.
- Les mesures GD@15/XPD@15 restent calculées uniquement sur les valeurs disponibles.
  Les parties trop courtes ou les timelines absentes ne deviennent pas des zéros.

La lecture complète des lignes de lane convient au volume actuel ; pour des historiques
beaucoup plus volumineux, prévoir des agrégats et une pagination côté serveur.

## Mise en service

Après push/pull, reconstruire le service web :

```bash
docker compose up -d --build web
```

Aucun changement de schéma SQL pour cette correction. Les collectes et builds dbt
habituels doivent continuer à alimenter les tables Gold.
