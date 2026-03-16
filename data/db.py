import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "voltanet"),
        user=os.getenv("POSTGRES_USER", "voltanet_user"),
        password=os.getenv("POSTGRES_PASSWORD", "voltanet_secret_2025"),
    )


def fetch_cluster_snapshot():
    query = """
    WITH latest_per_meter AS (
        SELECT DISTINCT ON (meter_id)
            meter_id,
            time,
            kw_demand,
            solar_kw,
            battery_soc_pct
        FROM readings
        ORDER BY meter_id, time DESC
    )
    SELECT
        COUNT(*) AS active_nodes,
        COALESCE(SUM(kw_demand), 0) AS total_kw_demand,
        COALESCE(SUM(solar_kw), 0) AS total_solar_kw,
        COALESCE(AVG(battery_soc_pct), 0) AS avg_battery_soc_pct,
        MAX(time) AS latest_time
    FROM latest_per_meter;
    """

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()

        return {
            "active_nodes": int(row[0]) if row[0] is not None else 0,
            "total_kw_demand": float(row[1]) if row[1] is not None else 0.0,
            "total_solar_kw": float(row[2]) if row[2] is not None else 0.0,
            "avg_battery_soc_pct": float(row[3]) if row[3] is not None else 0.0,
            "latest_time": str(row[4]) if row[4] is not None else "N/A",
        }
    finally:
        conn.close()


def fetch_demand_timeseries():
    query = """
    SELECT
        time_bucket('5 seconds', time) AS bucket,
        AVG(kw_demand) AS avg_kw
    FROM readings
    WHERE time > NOW() - INTERVAL '5 minutes'
    GROUP BY bucket
    ORDER BY bucket;
    """

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

        times = [r[0] for r in rows]
        demand = [float(r[1]) for r in rows]
        return times, demand
    finally:
        conn.close()


def fetch_node_snapshot():
    query = """
    SELECT DISTINCT ON (meter_id)
        meter_id,
        kw_demand,
        solar_kw,
        battery_soc_pct,
        time
    FROM readings
    ORDER BY meter_id, time DESC;
    """

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

        nodes = []
        for r in rows:
            nodes.append(
                {
                    "meter_id": r[0],
                    "kw_demand": float(r[1]) if r[1] is not None else 0.0,
                    "solar_kw": float(r[2]) if r[2] is not None else 0.0,
                    "battery_soc": float(r[3]) if r[3] is not None else 0.0,
                    "time": r[4],
                }
            )
        return nodes
    finally:
        conn.close()