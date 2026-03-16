// -------------------------------------------------------------
// VoltaNet Meter Agent
// -------------------------------------------------------------
// This program simulates a cluster of SME smart meters and
// publishes telemetry to the MQTT broker.
//
// Current data flow:
//
//   meter-agent (Rust, host)
//        -> MQTT broker (Mosquitto in Docker, host port 1884)
//        -> ingestor.py (Python, host)
//        -> TimescaleDB (Docker, host port 5432)
//
// This is the "edge telemetry" layer of the VoltaNet platform.
// -------------------------------------------------------------

// Serde lets us serialize Rust structs into JSON strings.
use serde::{Deserialize, Serialize};

// Chrono gives us UTC timestamps and access to the current hour,
// which we use to simulate daylight-dependent solar output.
use chrono::{Timelike, Utc};

// Random number generation is used to add realistic fluctuations
// to each SME's base electrical demand.
use rand::Rng;

// Tokio provides async scheduling primitives.
// We use `interval` to trigger a reading every 250 ms.
use tokio::time::{interval, Duration};

// rumqttc is the MQTT client library.
// AsyncClient publishes readings, MqttOptions configures the connection.
use rumqttc::{AsyncClient, MqttOptions, QoS};

// std::env allows us to read MQTT host/port from environment
// variables instead of hardcoding them.
use std::env;

// -------------------------------------------------------------
// TELEMETRY DATA MODEL
// -------------------------------------------------------------
// This struct is the exact JSON shape sent over MQTT.
//
// Each published packet represents one meter reading for one SME.
// The Python ingestor expects these exact fields and inserts them
// into TimescaleDB.
//
// NOTE:
// Keep this schema stable unless you update the ingestor and DB too.
#[derive(Debug, Serialize, Deserialize)]
pub struct MeterReading {
    // Unique identifier for the SME meter.
    // Example: "bakery_01"
    pub meter_id: String,

    // Timestamp in Unix milliseconds.
    // The ingestor converts this into TIMESTAMPTZ for Postgres.
    pub timestamp_ms: i64,

    // Instantaneous electrical demand in kilowatts.
    pub kw_demand: f64,

    // Cumulative imported energy in kWh.
    // This is the energy the SME consumed from the grid/cluster.
    pub kwh_import: f64,

    // Cumulative exported energy in kWh.
    // This is the energy the SME pushed back into the cluster.
    pub kwh_export: f64,

    // Battery state of charge as a percentage.
    // Published as a percentage because it is intuitive for dashboards.
    pub battery_soc_pct: f64,

    // Instantaneous solar generation in kilowatts.
    pub solar_kw: f64,
}

impl MeterReading {
    // Convenience constructor.
    // Creates a telemetry packet stamped with the current UTC time.
    pub fn new(
        meter_id: &str,
        kw_demand: f64,
        kwh_import: f64,
        kwh_export: f64,
        battery_soc_pct: f64,
        solar_kw: f64,
    ) -> Self {
        Self {
            meter_id: meter_id.to_string(),
            timestamp_ms: Utc::now().timestamp_millis(),
            kw_demand,
            kwh_import,
            kwh_export,
            battery_soc_pct,
            solar_kw,
        }
    }
}

// -------------------------------------------------------------
// SME PROFILE MODEL
// -------------------------------------------------------------
// This struct stores the static and dynamic properties of one SME.
//
// Static fields:
//   - base load
//   - solar capacity
//   - battery capacity
//
// Dynamic field:
//   - current battery energy (SOC in kWh)
//
// IMPORTANT:
// We store battery SOC internally in kWh, not percent.
// That keeps the battery math physically consistent.
pub struct SmeProfile {
    // Unique meter identifier.
    pub meter_id: String,

    // Typical electrical demand for this SME.
    pub base_load_kw: f64,

    // Rooftop solar capacity.
    pub solar_capacity_kw: f64,

    // Total battery capacity.
    pub battery_capacity_kwh: f64,

    // Current battery energy stored, in kWh.
    pub battery_soc_kwh: f64,
}

impl SmeProfile {
    // Create a new SME profile.
    // We initialize batteries at 80% full to make the simulation
    // look realistic for a daytime resilience scenario.
    pub fn new(
        meter_id: &str,
        base_load_kw: f64,
        solar_capacity_kw: f64,
        battery_capacity_kwh: f64,
    ) -> Self {
        Self {
            meter_id: meter_id.to_string(),
            base_load_kw,
            solar_capacity_kw,
            battery_capacity_kwh,
            battery_soc_kwh: battery_capacity_kwh * 0.8,
        }
    }
}

// -------------------------------------------------------------
// DEFAULT MICROGRID CLUSTER
// -------------------------------------------------------------
// This defines the 10 SMEs in the simulated business park.
//
// The profiles are intentionally varied so the data feels real:
//   - cold storage = high constant load
//   - office = moderate daytime load
//   - bakery = strong production load
//   - pharmacy = critical small-but-important load
pub fn default_cluster() -> Vec<SmeProfile> {
    vec![
        SmeProfile::new("bakery_01", 15.0, 10.0, 20.0),
        SmeProfile::new("office_01", 8.0, 6.0, 15.0),
        SmeProfile::new("cold_storage_01", 20.0, 8.0, 30.0),
        SmeProfile::new("retail_01", 10.0, 5.0, 12.0),
        SmeProfile::new("cafe_01", 6.0, 4.0, 10.0),
        SmeProfile::new("workshop_01", 12.0, 7.0, 18.0),
        SmeProfile::new("pharmacy_01", 7.0, 5.0, 12.0),
        SmeProfile::new("laundry_01", 14.0, 6.0, 15.0),
        SmeProfile::new("butchery_01", 18.0, 9.0, 25.0),
        SmeProfile::new("office_02", 8.0, 6.0, 15.0),
    ]
}

// -------------------------------------------------------------
// READING SIMULATION
// -------------------------------------------------------------
// Generates one realistic reading for a given SME profile.
//
// Simulation logic:
//   1. Start from base load
//   2. Apply +/- 10% random fluctuation
//   3. Generate solar from a simple daylight sine wave
//   4. Charge/discharge the battery depending on net load
//   5. Return a reading for this timestep
//
// Timestep:
//   250 ms = 0.25 seconds
pub fn simulate_reading(profile: &mut SmeProfile) -> MeterReading {
    let mut rng = rand::thread_rng();

    // Add random load variation to avoid synthetic flat lines.
    let noise = rng.gen_range(-0.1..=0.1);
    let kw_demand = profile.base_load_kw * (1.0 + noise);

    // Approximate solar generation using a sine wave between 06:00 and 18:00.
    // At night, solar is zero.
    let hour = Utc::now().hour() as f64;
    let solar_factor = if (6.0..=18.0).contains(&hour) {
        ((hour - 6.0) / 12.0 * std::f64::consts::PI).sin()
    } else {
        0.0
    };

    let solar_kw = profile.solar_capacity_kw * solar_factor;

    // Net power:
    // positive = importing power
    // negative = excess solar available
    let net_kw = kw_demand - solar_kw;

    // Convert the 250 ms interval into hours for kWh calculations.
    let dt_hours = 0.25 / 3600.0;

    // Battery behavior:
    // If solar exceeds demand, charge battery.
    // If demand exceeds solar, discharge battery.
    if net_kw < 0.0 {
        // Available surplus energy for charging this timestep.
        let charge_kwh = (-net_kw * dt_hours)
            .min(profile.battery_capacity_kwh - profile.battery_soc_kwh);

        profile.battery_soc_kwh += charge_kwh;
    } else {
        // Required battery discharge this timestep.
        let discharge_kwh = (net_kw * dt_hours).min(profile.battery_soc_kwh);

        profile.battery_soc_kwh -= discharge_kwh;
    }

    // Convert internal battery energy to percentage for publishing.
    let battery_soc_pct =
        (profile.battery_soc_kwh / profile.battery_capacity_kwh) * 100.0;

    // Energy import/export during this single timestep.
    //
    // NOTE:
    // These are incremental values for this reading only.
    // In main(), we accumulate them to produce cumulative counters.
    let kwh_import = if net_kw > 0.0 { net_kw * dt_hours } else { 0.0 };
    let kwh_export = if net_kw < 0.0 { -net_kw * dt_hours } else { 0.0 };

    MeterReading::new(
        &profile.meter_id,
        kw_demand,
        kwh_import,
        kwh_export,
        battery_soc_pct,
        solar_kw,
    )
}

// -------------------------------------------------------------
// APPLICATION ENTRY POINT
// -------------------------------------------------------------
// Creates one async task per SME and keeps publishing forever.
#[tokio::main]
async fn main() {
    println!("⚡ VoltaNet Meter Agent starting...");

    // Read MQTT connection settings from environment variables.
    //
    // Defaults are correct for the current setup:
    //   host machine -> Mosquitto published port
    let mqtt_host = env::var("MQTT_HOST").unwrap_or("127.0.0.1".into());

    let mqtt_port: u16 = env::var("MQTT_PORT")
        .unwrap_or("1884".into())
        .parse()
        .expect("MQTT_PORT must be a valid u16");

    // Load the simulated business park cluster.
    let mut cluster = default_cluster();

    // Store all spawned task handles so the program can await them.
    let mut handles = vec![];

    // Spawn one async publishing loop per SME node.
    for mut profile in cluster.drain(..) {
        let host = mqtt_host.clone();

        let handle = tokio::spawn(async move {
            println!("📡 Node {} online", profile.meter_id);

            // Each node gets its own MQTT client ID.
            // This makes broker logs and debugging much clearer.
            let mut mqtt_options = MqttOptions::new(
                format!("voltanet_{}", profile.meter_id),
                host,
                mqtt_port,
            );

            // Keep the MQTT session alive with periodic pings.
            mqtt_options.set_keep_alive(Duration::from_secs(30));

            // Create MQTT client and its internal event loop.
            let (client, mut eventloop) = AsyncClient::new(mqtt_options, 10);

            // The event loop must be polled continuously in the background.
            // Without this, the MQTT client will not actually function.
            tokio::spawn(async move {
                loop {
                    let _ = eventloop.poll().await;
                }
            });

            // 250 ms interval = telemetry heartbeat.
            let mut tick = interval(Duration::from_millis(250));

            // These hold cumulative imported/exported energy for the node.
            // They keep increasing over time, which is more realistic for billing.
            let mut cumulative_import = 0.0_f64;
            let mut cumulative_export = 0.0_f64;

            loop {
                tick.tick().await;

                // Generate one reading for this timestep.
                let reading = simulate_reading(&mut profile);

                // Accumulate incremental kWh values into cumulative counters.
                cumulative_import += reading.kwh_import;
                cumulative_export += reading.kwh_export;

                // Build the final published packet using cumulative values.
                let final_reading = MeterReading::new(
                    &profile.meter_id,
                    reading.kw_demand,
                    cumulative_import,
                    cumulative_export,
                    reading.battery_soc_pct,
                    reading.solar_kw,
                );

                // Convert Rust struct -> JSON string.
                let payload =
                    serde_json::to_string(&final_reading).unwrap();

                // Publish to this node's topic.
                //
                // Example topics:
                //   vn/telemetry/bakery_01
                //   vn/telemetry/office_01
                //
                // QoS::AtLeastOnce means MQTT will retry delivery if needed.
                // The ingestor handles possible duplicates with ON CONFLICT.
                let _ = client
                    .publish(
                        format!("vn/telemetry/{}", profile.meter_id),
                        QoS::AtLeastOnce,
                        false,
                        payload,
                    )
                    .await;
            }
        });

        handles.push(handle);
    }

    // Keep the main process alive forever by awaiting all tasks.
    // In practice, these loops run indefinitely until the program is stopped.
    for handle in handles {
        let _ = handle.await;
    }
}