use serde::{Deserialize, Serialize};
use chrono::{Utc, Timelike};
use rand::Rng;
use tokio::time::{interval, Duration};
use rumqttc::{MqttOptions, AsyncClient, QoS};

// ── DATA SHAPE ──────────────────────────────────────────────
// This is the exact packet every meter sends every 250ms.
// Every field maps directly to a column in TimescaleDB.

#[derive(Debug, Serialize, Deserialize)]
pub struct MeterReading {
    pub meter_id: String,        // unique node identifier e.g. "bakery_01"
    pub timestamp_ms: i64,       // unix milliseconds — TimescaleDB partitions on this
    pub kw_demand: f64,          // current power draw in kilowatts
    pub kwh_import: f64,         // cumulative energy pulled from grid or peers → what you're billed for
    pub kwh_export: f64,         // cumulative energy pushed to peers → what earns VoltaCredits
    pub battery_soc_pct: f64,    // battery state of charge 0–100%
    pub solar_kw: f64,           // current solar generation in kilowatts
}

impl MeterReading {
    // Constructor — captures the exact moment of reading via Utc::now()
    pub fn new(meter_id: &str, kw_demand: f64, kwh_import: f64,
               kwh_export: f64, battery_soc_pct: f64, solar_kw: f64) -> Self {
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

// ── SME PROFILES ────────────────────────────────────────────
// Each business on the cluster has different energy characteristics.
// These profiles drive realistic simulation — a bakery behaves
// nothing like a pharmacy. Real investors notice realistic data.

pub struct SmeProfile {
    pub meter_id: String,
    pub base_load_kw: f64,           // typical power draw for this business type
    pub solar_capacity_kw: f64,      // size of rooftop solar installation
    pub battery_capacity_kwh: f64,   // total battery storage available
    pub battery_soc: f64,            // current charge level — starts at 80% (realistic, not full)
}

impl SmeProfile {
    pub fn new(meter_id: &str, base_load_kw: f64,
               solar_capacity_kw: f64, battery_capacity_kwh: f64) -> Self {
        Self {
            meter_id: meter_id.to_string(),
            base_load_kw,
            solar_capacity_kw,
            battery_capacity_kwh,
            battery_soc: 80.0, // 80% = realistic overnight charge level
                               // 100% would look synthetic to any engineer
                               // 0% would mean no backup — defeats the demo
        }
    }
}

// ── CLUSTER DEFINITION ──────────────────────────────────────
// 10 SMEs on one industrial park — VoltaNet's target deployment unit.
// Each has different load, solar and storage characteristics
// reflecting real business diversity in a SA industrial estate.

pub fn default_cluster() -> Vec<SmeProfile> {
    vec![
        // meter_id            base_kw  solar_kw  battery_kwh
        SmeProfile::new("bakery_01",       15.0, 10.0, 20.0), // high AM load, good solar
        SmeProfile::new("office_01",        8.0,  6.0, 15.0), // steady 09-17 load
        SmeProfile::new("cold_storage_01", 20.0,  8.0, 30.0), // flat high load, needs most backup
        SmeProfile::new("retail_01",       10.0,  5.0, 12.0), // high PM load
        SmeProfile::new("cafe_01",          6.0,  4.0, 10.0), // peaks at breakfast and lunch
        SmeProfile::new("workshop_01",     12.0,  7.0, 18.0), // variable heavy equipment load
        SmeProfile::new("pharmacy_01",      7.0,  5.0, 12.0), // must-stay-on, critical load
        SmeProfile::new("laundry_01",      14.0,  6.0, 15.0), // high heat load through the day
        SmeProfile::new("butchery_01",     18.0,  9.0, 25.0), // refrigeration + equipment
        SmeProfile::new("office_02",        8.0,  6.0, 15.0), // second office unit
    ]
}

// ── READING SIMULATOR ────────────────────────────────────────
// Takes a live SME profile and generates a realistic meter reading.
// Called every 250ms per node — must be fast and stateful.
// "Stateful" means the battery level carries forward between reads.

pub fn simulate_reading(profile: &mut SmeProfile) -> MeterReading {
    let mut rng = rand::thread_rng();

    // Add ±10% randomness to base load — real businesses fluctuate
    let noise = rng.gen_range(-0.1..=0.1);
    let kw_demand = profile.base_load_kw * (1.0 + noise);

    // Solar generation — peaks midday, zero at night
    // We use a simple sine-wave approximation of daylight hours
    let hour = Utc::now().hour() as f64;
    let solar_factor = if hour >= 6.0 && hour <= 18.0 {
        ((hour - 6.0) / 12.0 * std::f64::consts::PI).sin()
    } else {
        0.0 // no solar generation at night
    };
    let solar_kw = profile.solar_capacity_kw * solar_factor;

    // Net power — positive means importing, negative means exporting
    let net_kw = kw_demand - solar_kw;

    // Battery logic — solar surplus charges battery, deficit draws it down
    let battery_delta = if net_kw < 0.0 {
        // surplus solar — charge battery, cap at 100%
        (net_kw.abs() * 0.25 / 3600.0)
            .min(profile.battery_capacity_kwh - profile.battery_soc)
    } else {
        // deficit — draw from battery, floor at 0%
        -(net_kw * 0.25 / 3600.0).min(profile.battery_soc)
    };
    profile.battery_soc = (profile.battery_soc + battery_delta).clamp(0.0, 100.0);

    // kwh counters — cumulative, always increasing
    let kwh_import = if net_kw > 0.0 { net_kw * 0.25 / 3600.0 } else { 0.0 };
    let kwh_export = if net_kw < 0.0 { net_kw.abs() * 0.25 / 3600.0 } else { 0.0 };

    MeterReading::new(
        &profile.meter_id,
        kw_demand,
        kwh_import,
        kwh_export,
        profile.battery_soc,
        solar_kw,
    )
}

// ── MAIN ENTRY POINT ─────────────────────────────────────────
// Spins up 10 async tasks — one per SME node.
// Each task runs its own 250ms publish loop independently.
// If one node slows down or errors, the others keep running.

#[tokio::main]
async fn main() {
    println!("⚡ VoltaNet Meter Agent starting...");

    // Load all 10 SME profiles
    let mut cluster = default_cluster();

    // Spawn one async task per meter
    let mut handles = vec![];

    for mut profile in cluster.drain(..) {
        let handle = tokio::spawn(async move {

            // Each meter gets its own MQTT client connection
            // Named uniquely so Mosquitto can track them individually
            let mut mqtt_options = MqttOptions::new(
                format!("voltanet_{}", profile.meter_id), // client id
                "localhost",                               // broker host
                1883,                                      // broker port
            );
            mqtt_options.set_keep_alive(Duration::from_secs(30));

            let (client, mut eventloop) = AsyncClient::new(mqtt_options, 10);

            // Drive the MQTT event loop in background
            // Without this the client won't send or receive anything
            tokio::spawn(async move {
                loop {
                    eventloop.poll().await.unwrap();
                }
            });

            // 250ms ticker — this is the heartbeat of the grid
            let mut tick = interval(Duration::from_millis(250));

            let mut cumulative_import = 0.0_f64;
            let mut cumulative_export = 0.0_f64;

            println!("📡 Node {} online", profile.meter_id);

            loop {
                tick.tick().await;

                // Generate a realistic reading for this node
                let reading = simulate_reading(&mut profile);

                // Accumulate cumulative kWh counters
                cumulative_import += reading.kwh_import;
                cumulative_export += reading.kwh_export;

                // Build the final reading with cumulative values
                let final_reading = MeterReading::new(
                    &profile.meter_id,
                    reading.kw_demand,
                    cumulative_import,
                    cumulative_export,
                    reading.battery_soc_pct,
                    reading.solar_kw,
                );

                // Serialise to JSON — this is what flows through Mosquitto
                let payload = serde_json::to_string(&final_reading).unwrap();

                // Publish to topic: vn/telemetry/{meter_id}
                // QoS::AtLeastOnce = guaranteed delivery, not fire-and-forget
                client.publish(
                    format!("vn/telemetry/{}", profile.meter_id),
                    QoS::AtLeastOnce,
                    false,
                    payload,
                ).await.unwrap();
            }
        });

        handles.push(handle);
    }

    // Wait for all 10 tasks — runs forever until killed
    for handle in handles {
        handle.await.unwrap();
    }
}



