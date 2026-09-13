"""Matchups: one valid participant per team/position, directional champion pairs."""


def matchups(frame):
    from pyspark.sql import Window
    from pyspark.sql import functions as f

    valid = frame.filter(
        f.col("team_position").isin("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
        & f.col("team_id").isin(100, 200)
        & f.col("champion_key").isNotNull()
        & f.col("patch").isNotNull()
        & f.col("win").isNotNull()
    )
    valid = valid.withColumn("slot_count", f.count("*").over(
        Window.partitionBy("match_id", "team_id", "team_position")
    )).filter("slot_count = 1")
    a, b = valid.alias("a"), valid.alias("b")
    pairs = a.join(b, (f.col("a.match_id") == f.col("b.match_id"))
                   & (f.col("a.team_position") == f.col("b.team_position"))
                   & (f.col("a.patch") == f.col("b.patch"))
                   & (f.col("a.team_id") != f.col("b.team_id")))
    return pairs.select(
        f.col("a.patch").alias("patch"), f.col("a.team_position").alias("role"),
        f.col("a.champion_key").alias("champion_key"),
        f.col("b.champion_key").alias("opponent_champion_key"),
        f.col("a.win").cast("int").alias("won"),
        (f.col("a.total_cs") - f.col("b.total_cs")).alias("cs_diff"),
        (f.col("a.gold_earned") - f.col("b.gold_earned")).alias("gold_diff"),
    ).groupBy("patch", "role", "champion_key", "opponent_champion_key").agg(
        f.count("*").alias("games"), f.sum("won").alias("wins"),
        f.avg("won").alias("win_rate"), f.avg("cs_diff").alias("avg_cs_diff"),
        f.avg("gold_diff").alias("avg_gold_diff"),
    )
