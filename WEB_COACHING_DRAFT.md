# Coaching, comptes pro et draft séparée

## Fonctionnement

- **Draft → SoloQ** : analyses Riot EUW existantes. Le score dbt utilise désormais
  60 % de présence soloQ, 20 % d'excès de winrate au-dessus de 45 %, 20 % de volume
  plafonné à 250 picks. Il ne reçoit plus de contribution professionnelle.
- **Draft → Pro** : sélection de patch indépendante, picks/bans/présence/winrate
  de `gold_pro_champion_draft_by_patch`. Toutes compétitions collectées confondues.
- **Coaching → Comparer** : chaque colonne propose les joueurs du roster
  (`club`/`academy`) ou les pros observés en compétition pendant l'année choisie.
  Les statistiques sont calculées sur l'année UTC entière, tous rôles et patches.
  Le nombre de parties renseignées accompagne chaque mesure. Aucun classement
  automatique de niveau entre pro et soloQ ; Gold@15 reste indisponible.
- Pour des filtres de compétition détaillés, conserver l'espace **Comparaison pro**.
- Les icônes utilisent le catalogue public officiel Data Dragon avec repli sur
  les références PostgreSQL. Si le CDN est inaccessible, les initiales restent
  affichées. Aucun jeton Riot n'est envoyé au navigateur.

## Comptes professionnels

La collecte Cargo existante demande déjà `Players.SoloqueueIds`. Le texte est
maintenant conservé dans `gold_pro_player_games.reported_soloqueue_accounts`
et affiché lors de la sélection d'un pro dans Coaching.

Leaguepedia décrit ce champ comme manuel, potentiellement incomplet ou inexact :
https://lol.fandom.com/wiki/Module:CargoDeclare/Players

Il ne garantit ni un Riot ID actuel, ni le serveur, ni la propriété du compte.
Vérifier le Riot ID et le serveur EUW puis utiliser le roster existant pour
l'enregistrer. Pas d'import massif automatique ni d'association par ressemblance
de pseudonyme. Le backend continue à lire uniquement les données autorisées.

## Après push / pull sur le VPS

1. Exécuter le DAG `leaguepedia_ingestion` jusqu'à la réussite du catalogue et du
   build Gold (il ajoute la colonne des comptes). Respecter ses limites Cargo.
2. Exécuter le DAG `dbt_transform` (tâche `dbt_build`) pour reconstruire les
   recommandations soloQ et la méta pro.
3. Reconstruire et remplacer le service web :

```bash
docker compose up -d --build --no-deps web
```

Actualiser la page. Si les nouveaux DAG/scripts ne sont pas encore chargés,
redémarrer Airflow selon la procédure existante du projet. Sans rebuild Gold,
la nouvelle route comptes peut retourner « données indisponibles ».

Vérification manuelle : sélectionner SoloQ puis Pro dans Draft (patches distincts),
ouvrir Coaching → Comparer, choisir un joueur suivi et un pro avec des parties
collectées la même année, vérifier sources, effectifs, comptes et icônes.
