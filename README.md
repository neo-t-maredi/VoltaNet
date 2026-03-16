# VoltaNet ⚡

Real-time microgrid telemetry and monitoring for distributed energy resource clusters.

VoltaNet streams live telemetry from simulated SME energy nodes through an MQTT pipeline, stores it in a time-series database, and visualises grid state through an interactive dashboard — refreshing every 2 seconds.

---

## Architecture

```
Rust Meter Agents
      ↓
MQTT Broker (Mosquitto)
      ↓
Python Ingestor
      ↓
TimescaleDB (PostgreSQL)
      ↓
Dash + Plotly Dashboard
```

---

## Features

- Real-time telemetry from distributed energy nodes
- Live cluster demand visualisation (5-minute rolling window)
- Battery state-of-charge monitoring with visual indicators
- Solar production tracking per node
- Time-series persistence via TimescaleDB
- Dashboard auto-refreshes every 2 seconds

---

## Simulated Nodes

Each node represents a typical SME energy consumer:

| Node | Type |
|------|------|
| Bakery | High heat demand |
| Cafe | Variable load |
| Retail | Steady commercial |
| Cold Storage | Continuous load |
| Pharmacy | Critical load |
| Workshop | Industrial demand |
| Laundry | Thermal + motor |
| Offices | Standard commercial |

Each node publishes the following telemetry per cycle:

- `kw_demand` — active power consumption
- `solar_kw` — solar generation output
- `battery_soc_pct` — battery state of charge (%)
- `timestamp`

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Simulation | Rust (meter agents) |
| Messaging | MQTT via Mosquitto |
| Ingestion | Python + async |
| Storage | TimescaleDB (PostgreSQL) |
| API | FastAPI |
| Dashboard | Dash + Plotly |
| Infrastructure | Docker Compose |

---

## Getting Started

### 1. Start infrastructure

```bash
docker compose up -d
```

### 2. Run meter simulation

```bash
cd services/meter-agent
cargo run
```

### 3. Start ingestor

```bash
cd services/api
source venv/bin/activate
python app/ingestor.py
```

### 4. Launch dashboard

```bash
python dashboard.py
```

Open [http://127.0.0.1:8050](http://127.0.0.1:8050)

---

## Dashboard

The dashboard displays three panels:

**Cluster summary**
- Total demand (kW)
- Active node count
- Aggregate solar generation
- Average battery SOC

**Time-series chart**
- Rolling 5-minute cluster demand

**Node telemetry table**
- Per-node demand, solar output, battery SOC, and visual battery bars

---

## Roadmap

- [ ] Grid topology visualisation
- [ ] Node geospatial map
- [ ] Anomaly detection
- [ ] Energy trading simulation
- [ ] WebSocket streaming
- [ ] React-based frontend

---

## Author

**Neo Maredi**  
Industrial Automation · Distributed Energy Systems · Edge Computing  
[github.com/neo-t-maredi/VoltaNet](https://github.com/neo-t-maredi/VoltaNet)