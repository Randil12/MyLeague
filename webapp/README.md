# MyLeague — interface coach et joueur

Interface française responsive, HTML/CSS/JavaScript natif, servie par FastAPI.
Pas de compilation Node nécessaire. L'API interroge PostgreSQL depuis Docker avec
le rôle `data_analyst` ; le navigateur ne reçoit aucun identifiant de connexion.
Les transactions sont en lecture seule et les requêtes limitées à 8 secondes.

## Fonctionnalités

- Méta : patch, recherche, rôle, minimum de picks, tri et accès aux builds.
- Draft : score dbt, niveau de confiance et exclusion des champions indisponibles.
- Entraînement : sélection Academy, maîtrise et priorités du modèle existant.
- Builds : objets et runes observés, volumes et taux de victoire.
- Évolution : comparaison au patch précédent disponible et variation en points.
- Niveaux : comparaison selon le tier du joueur source de la collecte.
- Supervision : historique des collectes et alertes, chargés indépendamment.
- Export CSV des résultats filtrés (taux bruts entre 0 et 1), protection contre
  les formules de tableur. La sélection de draft reste en mémoire dans l'onglet.

Toutes les données viennent des modèles Gold existants et des tables d'audit.
Le modèle Academy est limité au dernier patch et aux champions avec au moins
100 picks : un roster enregistré peut donc ne pas encore apparaître dans cette vue.
Aucun fallback inventé. Erreurs, tables absentes et échantillons vides sont
affichés explicitement. Le bouton Actualiser recharge les données ; il ne lance
ni collecte ni dbt. L'heure du dernier match n'est pas l'heure de calcul du Gold.

## Migration sur le VPS

Après le commit/push local, depuis `/home/ubuntu/MyLeague` :

```bash
git pull origin dev
# Libérer le port occupé par l'ancienne interface, sans supprimer ses fichiers.
docker compose --profile legacy stop streamlit
docker compose up -d --build web
docker compose ps web
curl --fail http://127.0.0.1:8501/healthz
```

Ne pas faire de `down -v` : les volumes PostgreSQL/MinIO doivent être conservés.
Les DAGs et les données ne sont pas remplacés. Le healthcheck confirme le
fonctionnement HTTP, pas la présence de données : vérifier ensuite chaque vue.

Depuis PowerShell sur le PC (laisser le tunnel ouvert) :

```powershell
ssh -N -L 127.0.0.1:18501:127.0.0.1:8501 root@IP_DU_VPS
```

Ouvrir `http://127.0.0.1:18501`. Adapter l'utilisateur SSH si nécessaire.
L'ancien tunnel vers le port VPS 8501 fonctionne également.

## Sécurité et périmètre

L'accès reste privé via SSH, comme l'ancienne interface. Aucun compte applicatif
ni séparation des droits coach/joueur n'est implémenté : les utilisateurs ayant
accès au tunnel voient les mêmes données, y compris le roster et la supervision.
Ne pas exposer directement le port sur Internet. Avant ouverture à une équipe
sans SSH, ajouter une authentification et HTTPS via un reverse proxy.

Le site n'implémente pas de live spectator, de calcul de timeline, de notes
persistantes ni de moteur de synergies. Les recommandations restent celles de dbt.
Les résultats de petits échantillons ne sont pas des preuves statistiques.

## Développement et tests

```bash
pip install -r requirements-dev.txt
uvicorn webapp.server:app --host 127.0.0.1 --port 8510
pytest tests/test_webapp.py -q
node --test tests/webapp_frontend.test.cjs
```

Configurer dans le terminal les variables `GOLD_POSTGRES_HOST`,
`GOLD_POSTGRES_PORT`, `GOLD_POSTGRES_DB`, `DATA_ANALYST_USER` et
`DATA_ANALYST_PASSWORD` pour joindre une vraie base. Ne jamais les ajouter au JS.
Le `.env` racine est injecté par Compose pour le déploiement, pas lu implicitement
par le serveur de développement. Les tests unitaires simulent les réponses SQL.

## Retour arrière

Le Streamlit original reste sous `app/`, activable sur le port VPS 8502 :

```bash
docker compose --profile legacy up -d --build streamlit
```

Cela ne modifie pas le site sur 8501. Utiliser un autre tunnel vers 8502.
