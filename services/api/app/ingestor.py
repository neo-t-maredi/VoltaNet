# Standard Python async runtime tools
import asyncio

# JSON is used because the Rust meter agents publish JSON payloads
import json

# OS access allows us to read environment variables
import os

# Used to convert the millisecond timestamps from Rust into
# proper PostgreSQL-compatible timestamps
from datetime import datetime, timezone

# Async MQTT client used to subscribe to telemetry messages
import aiomqtt

# Async PostgreSQL driver (very fast, production-grade)
import asyncpg

# Allows us to load variables from a local `.env` file
from dotenv import load_dotenv


# -------------------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# -------------------------------------------------------------
# This reads the `.env` file in the same directory and loads
# the variables into the OS environment.
#
# This means secrets like DB passwords never need to be
# hardcoded in the Python file.
load_dotenv()


# -------------------------------------------------------------
# MQTT CONFIGURATION
# -------------------------------------------------------------
# MQTT_BROKER
# Host address of the Mosquitto broker.
#
# Default is localhost because Docker exposes Mosquitto to
# the host via port mapping.
MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")

# MQTT_PORT
# Host-side port mapped to the Mosquitto container.
# Docker maps:
#
#   host 1884 -> container 1883
#
MQTT_PORT = int(os.getenv("MQTT_PORT", "1884"))

# MQTT_TOPIC
# Wildcard subscription to capture all telemetry topics.
#
# Example incoming topics:
#
# vn/telemetry/bakery_01
# vn/telemetry/office_01
#
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "vn/telemetry/#")


# -------------------------------------------------------------
# POSTGRES / TIMESCALE CONFIGURATION
# -------------------------------------------------------------
# Host address for the database container.
# Docker exposes the container's port 5432 to localhost.
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")

# Database port
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))

# Database name
POSTGRES_DB = os.getenv("POSTGRES_DB", "voltanet")

# Database username
POSTGRES_USER = os.getenv("POSTGRES_USER", "voltanet_user")

# Database password
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "voltanet_secret_2025")


# -------------------------------------------------------------
# DATABASE SCHEMA
# -------------------------------------------------------------
# This table stores every telemetry reading from every meter.
#
# One row = one reading from one SME node.
#
# The "UNIQUE (meter_id, time)" constraint ensures that
# duplicate MQTT deliveries (which happen with QoS1) do not
# create duplicate database rows.

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS readings (
    time            TIMESTAMPTZ       NOT NULL,
    meter_id        TEXT              NOT NULL,
    kw_demand       DOUBLE PRECISION  NOT NULL,
    kwh_import      DOUBLE PRECISION  NOT NULL,
    kwh_export      DOUBLE PRECISION  NOT NULL,
    battery_soc_pct DOUBLE PRECISION  NOT NULL,
    solar_kw        DOUBLE PRECISION  NOT NULL,
    CONSTRAINT readings_meter_time_unique UNIQUE (meter_id, time)
);
"""


# Convert the table into a TimescaleDB hypertable.
#
# TimescaleDB partitions time-series data automatically
# for high performance queries over time windows.
CREATE_HYPERTABLE_SQL = """
SELECT create_hypertable('readings', 'time', if_not_exists => TRUE);
"""


# Index used to quickly retrieve readings for a specific meter.
#
# Example query this speeds up:
#
#   "show last 24 hours for bakery_01"
#
CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_readings_meter_id_time
ON readings (meter_id, time DESC);
"""


# SQL statement used for inserting readings.
#
# ON CONFLICT DO NOTHING prevents duplicate rows
# when MQTT redelivers a message.
INSERT_SQL = """
INSERT INTO readings (
    time,
    meter_id,
    kw_demand,
    kwh_import,
    kwh_export,
    battery_soc_pct,
    solar_kw
) VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT DO NOTHING;
"""


# -------------------------------------------------------------
# SIMPLE LOGGER
# -------------------------------------------------------------
# Small helper to keep console output consistent.
def log(message: str) -> None:
    print(f"[ingestor] {message}", flush=True)


# -------------------------------------------------------------
# WAIT FOR DATABASE
# -------------------------------------------------------------
# Docker containers may take a few seconds to start.
#
# This function retries the connection until Postgres
# becomes available.
async def wait_for_postgres() -> asyncpg.Connection:

    while True:
        try:
            conn = await asyncpg.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                database=POSTGRES_DB,
            )

            log(
                f"Connected to TimescaleDB at "
                f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
            )

            return conn

        except Exception as exc:
            log(f"Postgres not ready yet: {exc}")
            await asyncio.sleep(2)


# -------------------------------------------------------------
# DATABASE INITIALISATION
# -------------------------------------------------------------
# Creates the table and converts it into a hypertable.
#
# Safe to run every startup because IF NOT EXISTS is used.
async def init_db(conn: asyncpg.Connection) -> None:

    await conn.execute(CREATE_TABLE_SQL)
    await conn.execute(CREATE_HYPERTABLE_SQL)
    await conn.execute(CREATE_INDEX_SQL)

    log("Database schema ready")


# -------------------------------------------------------------
# MQTT MESSAGE PARSER
# -------------------------------------------------------------
# Converts the raw MQTT payload into values ready for SQL insertion.
#
# Rust publishes telemetry packets that look like:
#
# {
#   "meter_id": "bakery_01",
#   "timestamp_ms": 1741272000000,
#   "kw_demand": 12.3,
#   "kwh_import": 1.2,
#   "kwh_export": 0.4,
#   "battery_soc_pct": 78.1,
#   "solar_kw": 5.4
# }
#
def parse_payload(payload: bytes) -> tuple:

    # Convert bytes -> JSON dictionary
    data = json.loads(payload.decode("utf-8"))

    # Convert milliseconds -> proper timestamp
    ts = datetime.fromtimestamp(
        data["timestamp_ms"] / 1000.0,
        tz=timezone.utc,
    )

    # Return tuple matching the SQL INSERT placeholders
    return (
        ts,
        str(data["meter_id"]),
        float(data["kw_demand"]),
        float(data["kwh_import"]),
        float(data["kwh_export"]),
        float(data["battery_soc_pct"]),
        float(data["solar_kw"]),
    )


# -------------------------------------------------------------
# MQTT CONSUMER LOOP
# -------------------------------------------------------------
# Connects to Mosquitto and continuously consumes telemetry.
#
# If the broker disconnects, the loop restarts automatically.
async def consume_messages(conn: asyncpg.Connection) -> None:

    while True:

        try:
            log(f"Connecting to MQTT at {MQTT_BROKER}:{MQTT_PORT}")

            async with aiomqtt.Client(
                hostname=MQTT_BROKER,
                port=MQTT_PORT,
            ) as client:

                log("Connected to MQTT broker")

                await client.subscribe(MQTT_TOPIC)

                log(f"Subscribed to {MQTT_TOPIC}")

                # Infinite async message stream
                async for message in client.messages:

                    try:
                        values = parse_payload(message.payload)

                        await conn.execute(INSERT_SQL, *values)

                        log(
                            f"Stored reading: "
                            f"meter_id={values[1]} "
                            f"time={values[0].isoformat()} "
                            f"kw={values[2]:.2f}"
                        )

                    except Exception as exc:
                        log(f"Failed to process message: {exc}")
                        log(f"Raw payload: {message.payload!r}")

        except Exception as exc:
            log(f"MQTT connection failed or dropped: {exc}")
            await asyncio.sleep(2)


# -------------------------------------------------------------
# MAIN PROGRAM
# -------------------------------------------------------------
# Startup flow:
#
# 1. Wait for database
# 2. Create schema
# 3. Start MQTT consumer loop
#
async def main() -> None:

    log("VoltaNet Ingestor starting")

    conn = await wait_for_postgres()

    try:
        await init_db(conn)

        await consume_messages(conn)

    finally:
        await conn.close()
        log("Postgres connection closed")


# Python program entry point
if __name__ == "__main__":
    asyncio.run(main())

