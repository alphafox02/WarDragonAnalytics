# WarDragon Analytics

**Multi-kit drone surveillance aggregation and visualization platform**

Centralized logging, analysis, and visualization of data from one or more WarDragon kits running [DragonSync](https://github.com/alphafox02/DragonSync).

---

## Status: 🚧 Planning/Design Phase

This project is in the planning stage. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

---

## What It Does

- **Aggregates data** from multiple WarDragon kits via the DragonSync API
- **Stores time-series data** in TimescaleDB (PostgreSQL extension)
- **Visualizes** drone tracks, FPV signals, and system health in Grafana + custom web UI
- **Exports** data to CSV, KML (Google Earth)
- **Monitors** kit health and availability
- **Runs anywhere:** Docker container (local on kit, centralized server, or cloud)

---

## Architecture Overview

```
WarDragon Kits (Field)  →  Analytics (Docker)  →  Grafana/Web UI
   DragonSync APIs          TimescaleDB            Maps, Dashboards
   :8088                    Collector Service      CSV/KML Export
```

**Data Sources:**
- Drones (Remote ID: DJI, BLE, Wi-Fi)
- Aircraft (ADS-B tracks)
- FPV Signals (5.8GHz analog, DJI)
- System Health (GPS, CPU, memory, temps)

**Components:**
- **TimescaleDB:** Time-series database (30-day retention, 1-year aggregates)
- **Collector:** Python service polling DragonSync APIs every 5s
- **Web UI:** FastAPI + Leaflet map (all kits combined)
- **Grafana:** Pre-built dashboards for operations, health, analytics

---

## Quick Start (When Ready)

```bash
# Clone repo
git clone https://github.com/yourusername/WarDragonAnalytics.git
cd WarDragonAnalytics

# Configure kits
cp config/kits.yaml.example config/kits.yaml
# Edit kits.yaml to add your WarDragon kit IPs

# Set passwords
cp .env.example .env
# Edit .env to set DB and Grafana passwords

# Start services
docker-compose up -d

# Access UIs
# Web UI:  http://localhost:8080
# Grafana: http://localhost:3000  (admin / <GRAFANA_PASSWORD>)
```

---

## Deployment Options

### Option 1: Centralized Server (Recommended)
- Deploy Analytics on a server/cloud instance
- Configure multiple kits to report to it
- Best for operations with 3+ kits

### Option 2: Per-Kit Local
- Deploy Analytics alongside DragonSync on the same kit
- Point at `http://127.0.0.1:8088`
- Best for single-kit deployments or field testing

### Option 3: Hybrid
- Some kits report to central Analytics
- Some run local Analytics instances
- Best for mixed deployments (HQ + field units)

---

## Features Roadmap

### Phase 1: MVP ✅ (Planning Complete)
- [x] Architecture design
- [ ] TimescaleDB schema + init scripts
- [ ] Collector service (basic polling)
- [ ] Web UI (Leaflet map + table)
- [ ] Docker Compose deployment

### Phase 2: Multi-Kit
- [ ] Kit management UI
- [ ] Health monitoring
- [ ] Grafana dashboards
- [ ] CSV/KML export

### Phase 3: Advanced
- [ ] Geofencing alerts
- [ ] RID watchlist
- [ ] Continuous aggregates
- [ ] Data retention policies

### Phase 4: Production
- [ ] Authentication
- [ ] API keys
- [ ] Alert webhooks
- [ ] Mobile UI

---

## Requirements

**Server/Host:**
- Docker + Docker Compose
- 2GB RAM minimum (4GB recommended for multi-kit)
- 50GB disk (for 30 days of 5-kit data)

**WarDragon Kits:**
- DragonSync v2.0+ with API enabled (default port 8088)
- Network connectivity to Analytics host

---

## Documentation

- [Architecture Design](docs/ARCHITECTURE.md) - Full system design, database schema, APIs
- [Development Guide](docs/DEVELOPMENT.md) - How to contribute (coming soon)
- [Deployment Guide](docs/DEPLOYMENT.md) - Production deployment best practices (coming soon)

---

## Related Projects

- **[DragonSync](https://github.com/alphafox02/DragonSync)** - Drone detection and TAK integration (runs on WarDragon kits)
- **[WarDragon](https://github.com/alphafox02/WarDragon)** - Hardware platform for drone detection
- **[DragonOS](https://cemaxecuter.com/)** - Custom Linux distribution for SDR and drone detection

---

## License

Apache 2.0 (same as DragonSync)

---

## Contributing

This project is in early planning. Contributions welcome once MVP is implemented.

**To contribute:**
1. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
2. Open an issue to discuss your idea
3. Fork, implement, test, submit PR

---

## Contact

- **Issues:** [GitHub Issues](https://github.com/yourusername/WarDragonAnalytics/issues)
- **DragonSync:** [alphafox02/DragonSync](https://github.com/alphafox02/DragonSync)

---

**Note:** This is a companion project to DragonSync. It does not replace on-kit logging (use `drone_logger.py` + `log_viewer.py` for that). Analytics is for multi-kit aggregation and advanced visualization.
