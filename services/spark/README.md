# Spark : match-ups distribués

## Architecture et périmètre

Airflow `spark_matchups` → lanceur interne → `spark-submit` → master + deux workers
→ `gold.spark_champion_matchups`. Aucune exposition publique, aucun Docker socket.
Le calcul utilise les participants classés solo de `gold.fact_match_participant`
(donc ingestion Riot et **dbt build réussi requis**), pas les parties Leaguepedia.

Spark lit quatre partitions JDBC d'un instantané cohérent, joint les adversaires
par partie et rôle, puis agrège par patch/champion/adversaire. Les slots ambigus
(plusieurs participants au même poste dans une équipe) sont exclus.
Résultats directionnels : games, wins, win_rate (0..1), différences moyennes de CS
et d'or **en fin de partie**, pas à 15 minutes. Un match peut apparaître dans les
deux sens : ne pas sommer les lignes comme un nombre de matchs uniques.
Toujours interpréter le taux de victoire avec l'effectif ; aucune causalité garantie.

Deux workers d'un cœur, executors de 768 Mio, driver de 512 Mio ; limites Docker
cumulées de 5 Gio environ (master, workers, runner), en plus de la stack existante.
Le profil est optionnel pour un VPS de 12 Go. Éviter une ingestion lourde en parallèle
et surveiller `docker stats`. Pas de gain de performance promis à faible volume.
Deux conteneurs sur le même VPS démontrent un calcul distribué entre processus,
pas de haute disponibilité ni de distribution sur plusieurs machines physiques.

## Lancement VPS

Après commit/push local, sur le VPS :

```bash
cd /home/ubuntu/MyLeague
git pull origin dev
docker compose --profile spark up -d --build spark-master spark-worker-1 spark-worker-2 spark-runner
docker compose restart airflow
docker compose --profile spark ps
```

Les identifiants PostgreSQL existants sont réutilisés, sans nouveau secret.
Le lanceur utilise le compte technique Gold ; `data_analyst` ne reçoit que SELECT.
Le DAG est **manuel**, sans retry automatique : déclencher `spark_matchups` dans
Airflow après un build dbt réussi. Il attend le résultat (20 minutes maximum).
Pas de dépendance automatique avec dbt, ni de nouveau calcul dans le DAG temps réel.
Un seul lancement à la fois ; verrou SQL commun aux exécutions du job.

## Test synthétique avant les données réelles

Dans un terminal VPS, après démarrage du cluster :

```bash
docker compose --profile spark exec spark-runner /opt/spark/bin/spark-submit --master spark://spark-master:7077 --deploy-mode client --driver-memory 512m --executor-memory 768m --executor-cores 1 --total-executor-cores 2 --conf spark.driver.host=spark-runner --conf spark.driver.bindAddress=0.0.0.0 --py-files /opt/myleague/transform.py /opt/myleague/smoke.py
```

Ce test utilise uniquement des données fictives et ne touche pas PostgreSQL.
Attendre `PASS`, puis déclencher le DAG réel. Ne pas lancer le test et le DAG ensemble.

## Résultats et preuve de distribution

Depuis DBeaver :

```sql
SELECT * FROM gold.spark_champion_matchups WHERE games >= 10 ORDER BY games DESC LIMIT 100;
SELECT * FROM audit.spark_matchup_runs ORDER BY completed_at DESC LIMIT 10;
```

La première table n'apparaît qu'après un calcul réussi. Les résultats sont publiés
dans une transaction ; en cas d'erreur l'ancien résultat reste accessible. Un
résultat vide ou dépassant 100 000 groupes est refusé. Les tables dbt restent intactes.
L'instantané `raw.spark_matchup_input` est réservé au job et remplacé à chaque run ;
prévoir l'espace pour cette copie des huit colonnes nécessaires. Pas de PUUID copié.
L'audit conserve les succès ; les erreurs sont dans Airflow et les logs du runner.
La table est exploitable via SQL/Grafana ; elle n'est pas encore intégrée à une
nouvelle page dans l'application web.

Ajouter au tunnel SSH local :

```bash
-L 18081:127.0.0.1:18081 -L 14040:127.0.0.1:14040
```

Master : http://localhost:18081 (deux workers ALIVE).
Pendant le calcul uniquement : http://localhost:14040, onglets Executors / Stages.
Vérifier des tâches terminées sur **chacun des deux executors** ; le nombre de
partitions seul ne suffit pas comme preuve. Conserver une capture pendant le run.
Le job réel refuse le mode local et attend deux executors enregistrés avant le calcul.
Les liens internes des interfaces peuvent nécessiter des tunnels supplémentaires.

```bash
docker compose logs --tail=100 spark-runner spark-worker-1 spark-worker-2
docker compose --profile spark stop spark-runner spark-worker-1 spark-worker-2 spark-master
```

Arrêter uniquement une fois le DAG terminé. Pour relancer : même commande `up`.
L'API interne du lanceur n'a pas d'authentification applicative : ne jamais publier
8090, 7077 ou le réseau du cluster sur Internet. Les interfaces privées ne sont pas
des interfaces publiques sécurisées. Les événements Spark ne sont pas archivés dans
un History Server ; la preuve détaillée d'exécution doit être capturée pendant le run.

Références : [Spark standalone](https://spark.apache.org/docs/3.5.8/spark-standalone.html),
[JDBC partitionné](https://spark.apache.org/docs/3.5.8/sql-data-sources-jdbc.html).
