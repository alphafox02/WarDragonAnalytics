# Test Data Generator for WarDragon Analytics

## Overview

`test_data_generator.py` generates realistic fake drone detection data for testing the WarDragon Analytics platform. It simulates:

- **Multiple WarDragon kits** at different GPS locations
- **Realistic drone tracks** with GPS waypoints and flight characteristics
- **FPV signal detections** (5.8 GHz analog and DJI Digital)
- **System health metrics** (CPU, memory, disk, temps, GPS)
- **Time progression** over a configurable duration

## Installation

### Dependencies

For **SQL output mode** (default):
```bash
# No additional dependencies required
python app/test_data_generator.py --mode=sql --duration=1h > test_data.sql
```

For **database mode**:
```bash
# Install psycopg2 for direct database writes
pip install psycopg2-binary
```

## Usage

### Basic Examples

```bash
# Generate 2 hours of test data for 3 kits, write directly to database
python app/test_data_generator.py --mode=db --duration=2h --kits=3 --drones=15

# Generate SQL INSERT statements (for manual import or inspection)
python app/test_data_generator.py --mode=sql --duration=1h --kits=1 --drones=5

# Save SQL to file
python app/test_data_generator.py --mode=sql --duration=30m > test_data.sql
psql -U wardragon -d wardragon -f test_data.sql
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--mode` | Output mode: `sql` (print SQL) or `db` (write to database) | `sql` |
| `--duration` | Duration of data to generate (e.g., `2h`, `30m`, `1h30m`) | `2h` |
| `--kits` | Number of kits to simulate | `3` |
| `--drones` | Average number of drones per kit | `15` |
| `--db-url` | PostgreSQL connection URL (for `--mode=db`) | `postgresql://wardragon:wardragon@localhost:5432/wardragon` |
| `--signal-probability` | Probability of FPV signal per 5s interval (0.0-1.0) | `0.3` |

### Advanced Examples

```bash
# Small dataset for quick testing
python app/test_data_generator.py --mode=db --duration=15m --kits=1 --drones=3

# Large dataset with many signals
python app/test_data_generator.py --mode=db --duration=4h --kits=5 --drones=20 --signal-probability=0.6

# Custom database connection
python app/test_data_generator.py \
  --mode=db \
  --duration=1h \
  --db-url="postgresql://admin:secret@analytics.example.com:5432/wardragon"

# Generate SQL for specific time period
python app/test_data_generator.py --mode=sql --duration=2h30m --kits=2
```

## Generated Data

### Kits
- **Location**: Realistic GPS coordinates from major US cities
- **Status**: All kits marked as "online"
- **API URLs**: Simulated local network addresses

### Drone Tracks
- **Makes/Models**: DJI (Mini 3 Pro, Mavic 3, Air 3, etc.), Autel, Skydio, Parrot
- **Flight patterns**: Random waypoint-based flights (3-8 waypoints)
- **Duration**: 5-45 minutes per flight
- **Speed**: 5-20 m/s
- **Altitude**: 30-120 meters
- **Remote ID**: Realistic operator IDs, serial numbers, MAC addresses
- **Updates**: Position every 5 seconds (matching DragonSync poll rate)

### FPV Signals
- **Analog FPV**: 5.8 GHz frequencies (Bands A, B, E, F, R)
- **DJI Digital**: 5725-5865 MHz
- **Power levels**: -85 to -45 dBm
- **Detection rate**: Configurable probability (default 30% per 5s interval)

### System Health
- **GPS**: Stationary kit position with realistic GPS jitter
- **Metrics**: CPU (20-60%), Memory (40-70%), Disk (30-52%)
- **Temperatures**: CPU (40-70°C), GPU (35-60°C)
- **Updates**: Every 30 seconds
- **Uptime**: Starts at simulation start time

## Database Schema

The generator expects TimescaleDB tables as defined in [architecture.md](architecture.md):

- `kits` - Kit registry
- `drones` (hypertable) - Drone/aircraft tracks
- `signals` (hypertable) - FPV signal detections
- `system_health` (hypertable) - Kit health metrics

## Performance

### Typical Generation Rates

| Duration | Kits | Drones | Records Generated | Time (db mode) |
|----------|------|--------|-------------------|----------------|
| 15m | 1 | 5 | ~1,500 | ~5 seconds |
| 1h | 3 | 15 | ~20,000 | ~15 seconds |
| 2h | 3 | 15 | ~40,000 | ~30 seconds |
| 4h | 5 | 20 | ~120,000 | ~2 minutes |

### Batch Inserts
- Uses `psycopg2.extras.execute_batch()` for efficient bulk inserts
- Batch size: 1,000 records
- ON CONFLICT handling prevents duplicate data

## Troubleshooting

### "psycopg2 not installed" error
```bash
pip install psycopg2-binary
```

### Database connection failed
```bash
# Check TimescaleDB is running
docker ps | grep timescale

# Test connection manually
psql -U wardragon -h localhost -d wardragon

# Verify connection string
python app/test_data_generator.py --mode=db --db-url="postgresql://user:pass@host:port/db"
```

### Too much data generated
```bash
# Reduce duration and number of drones
python app/test_data_generator.py --mode=db --duration=30m --kits=2 --drones=5

# Lower signal detection probability
python app/test_data_generator.py --mode=db --signal-probability=0.1
```

### SQL output too large
```bash
# Generate smaller dataset
python app/test_data_generator.py --mode=sql --duration=15m --kits=1 > small_test.sql

# Or pipe directly to database
python app/test_data_generator.py --mode=sql --duration=1h | psql -U wardragon -d wardragon
```

## Integration with Analytics UI

After generating test data:

1. **Web UI**: Navigate to `http://localhost:8090` to see drone tracks on the map
2. **Grafana**: View pre-built dashboards at `http://localhost:3000`
3. **Verify data**: Query database directly
   ```sql
   SELECT COUNT(*) FROM drones;
   SELECT COUNT(*) FROM signals;
   SELECT COUNT(*) FROM system_health;
   SELECT * FROM kits;
   ```

## Data Characteristics

### Realistic Elements
- **GPS trajectories**: Drones follow waypoint-based flight paths
- **Speed variation**: Speeds vary during flight (50-100% of max speed)
- **Heading calculation**: Calculated based on direction of travel
- **Pilot location**: Stays fixed, within 5km of kit
- **Home point**: Set at pilot location
- **RSSI**: Realistic signal strength (-90 to -40 dBm)
- **Time progression**: Data covers entire duration with 5s intervals

### Limitations
- **No terrain awareness**: Drones don't avoid obstacles
- **Simplified physics**: Linear interpolation between waypoints
- **Random flight patterns**: Not based on real-world mission profiles
- **Static pilot**: Pilot doesn't move during flight

## Future Enhancements

Potential improvements:
- [ ] Aircraft (ADS-B) track generation
- [ ] Geofence violations
- [ ] Multi-day data generation
- [ ] CSV export support
- [ ] Configuration file for custom scenarios
- [ ] Mission templates (survey, inspection, patrol)
- [ ] Terrain-aware flight paths

## License

Apache 2.0 (same as DragonSync and WarDragon Analytics)
