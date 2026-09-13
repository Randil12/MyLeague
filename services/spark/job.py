"""Fixed, bounded Spark job. Only its own derived tables are replaced."""
import os
import time

import psycopg2
from psycopg2.extras import execute_values
from pyspark.sql import SparkSession
from transform import matchups


def connect():
    return psycopg2.connect(
        host=os.getenv("GOLD_POSTGRES_HOST", "gold-postgres"),
        port=os.getenv("GOLD_POSTGRES_PORT", "5432"),
        dbname=os.getenv("GOLD_POSTGRES_DB", "gold"),
        user=os.getenv("GOLD_POSTGRES_USER", "gold"),
        password=os.environ["GOLD_POSTGRES_PASSWORD"], connect_timeout=10,
    )


def run():
    conn = connect()
    spark = None
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout='120s'")
            cur.execute("SELECT pg_try_advisory_lock(74120502)")
            if not cur.fetchone()[0]:
                raise RuntimeError("Another matchup computation is running")
            # Materialize a consistent snapshot: dbt may replace its own fact table later.
            cur.execute("""CREATE TABLE IF NOT EXISTS raw.spark_matchup_input AS
                SELECT match_id, patch, team_id, team_position, champion_key,
                       win, total_cs, gold_earned
                FROM gold.fact_match_participant WITH NO DATA""")
            cur.execute("TRUNCATE raw.spark_matchup_input")
            cur.execute("""INSERT INTO raw.spark_matchup_input
                SELECT match_id, patch, team_id, team_position, champion_key,
                       win, total_cs, gold_earned FROM gold.fact_match_participant""")
            input_rows = cur.rowcount
            if not input_rows:
                raise RuntimeError("No input data: run Riot ingestion and dbt first")
        conn.commit()
        spark = (SparkSession.builder.appName("MyLeague champion matchups")
                 .config("spark.sql.shuffle.partitions", "4")
                 .config("spark.sql.adaptive.enabled", "false")
                 .config("spark.sql.session.timeZone", "UTC").getOrCreate())
        if not spark.sparkContext.master.startswith("spark://"):
            raise RuntimeError("A standalone cluster is required, not local[*]")
        # Driver + two executors. Fail rather than claim a two-worker execution on one.
        deadline = time.monotonic() + 90
        while spark.sparkContext._jsc.sc().getExecutorMemoryStatus().size() < 3:
            if time.monotonic() > deadline:
                raise RuntimeError("Two registered executors required")
            time.sleep(2)
        url = (f"jdbc:postgresql://{os.getenv('GOLD_POSTGRES_HOST', 'gold-postgres')}:"
               f"{os.getenv('GOLD_POSTGRES_PORT', '5432')}/{os.getenv('GOLD_POSTGRES_DB', 'gold')}")
        frame = spark.read.jdbc(url, "raw.spark_matchup_input", predicates=[
            f"mod(hashtext(match_id)::bigint + 2147483648, 4) = {i}" for i in range(4)
        ], properties={"user": os.getenv("GOLD_POSTGRES_USER", "gold"),
                       "password": os.environ["GOLD_POSTGRES_PASSWORD"],
                       "driver": "org.postgresql.Driver", "fetchsize": "1000",
                       "queryTimeout": "120"})
        result = matchups(frame).persist()
        output_rows = result.count()
        if not 0 < output_rows <= 100000:
            raise RuntimeError("Empty or oversized matchup output; previous result preserved")
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS gold.spark_champion_matchups (
                patch text NOT NULL, role text NOT NULL, champion_key integer NOT NULL,
                opponent_champion_key integer NOT NULL, games bigint NOT NULL CHECK(games>0),
                wins bigint NOT NULL CHECK(wins>=0 AND wins<=games),
                win_rate double precision NOT NULL CHECK(win_rate BETWEEN 0 AND 1),
                avg_cs_diff double precision, avg_gold_diff double precision,
                computed_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY(patch,role,champion_key,opponent_champion_key));
                CREATE TABLE IF NOT EXISTS audit.spark_matchup_runs (
                    application_id text PRIMARY KEY, completed_at timestamptz DEFAULT now(),
                    input_rows bigint, output_rows bigint, partitions integer)
            """)
            # DELETE/INSERT in one transaction preserves grants and last good data on failure.
            cur.execute("DELETE FROM gold.spark_champion_matchups")
            batch = []
            for row in result.toLocalIterator():
                batch.append(tuple(row))
                if len(batch) == 500:
                    write_batch(cur, batch)
                    batch.clear()
            if batch:
                write_batch(cur, batch)
            cur.execute("GRANT SELECT ON gold.spark_champion_matchups, audit.spark_matchup_runs TO data_analyst")
            cur.execute("INSERT INTO audit.spark_matchup_runs(application_id,input_rows,output_rows,partitions) "
                        "VALUES (%s,%s,%s,4)", (spark.sparkContext.applicationId, input_rows, output_rows))
        conn.commit()
        print(f"Published {output_rows} matchups from {input_rows} participants; "
              f"application={spark.sparkContext.applicationId}", flush=True)
    finally:
        conn.close()
        if spark:
            spark.stop()


def write_batch(cur, batch):
    execute_values(cur, """INSERT INTO gold.spark_champion_matchups
        (patch,role,champion_key,opponent_champion_key,games,wins,win_rate,avg_cs_diff,avg_gold_diff)
        VALUES %s""", batch)


if __name__ == "__main__":
    run()
