"""Synthetic transformation test; never writes to PostgreSQL."""
from pyspark.sql import SparkSession
from transform import matchups

spark = SparkSession.builder.appName("MyLeague Spark synthetic test").getOrCreate()
try:
    fields = "match_id string, patch string, team_id int, team_position string, champion_key int, win boolean, total_cs int, gold_earned int"
    data = [
        ("m1", "26.18", 100, "TOP", 1, True, 200, 12000),
        ("m1", "26.18", 200, "TOP", 2, False, 180, 11000),
        ("m2", "26.18", 100, "TOP", 1, False, 150, 10000),
        ("m2", "26.18", 200, "TOP", 2, True, 180, 12000),
        # Invalid position and unmatched participant must not produce a matchup.
        ("m3", "26.18", 100, "", 1, True, 10, 1000),
        ("m4", "26.18", 100, "TOP", 1, True, 10, 1000),
    ]
    rows = matchups(spark.createDataFrame(data, fields).repartition(4)).collect()
    assert len(rows) == 2
    first = next(r for r in rows if r.champion_key == 1)
    assert first.games == 2 and first.wins == 1 and first.win_rate == 0.5
    assert first.avg_cs_diff == -5 and first.avg_gold_diff == -500
    duplicate = data + [data[0]]
    rows = matchups(spark.createDataFrame(duplicate, fields).repartition(4)).collect()
    assert len(rows) == 2 and all(r.games == 1 for r in rows)
    assert matchups(spark.createDataFrame([], fields)).count() == 0
    print("PASS: directional matchup aggregates, duplicate slots, missing opponents, empty data")
finally:
    spark.stop()
