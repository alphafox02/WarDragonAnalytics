# MQTT Ingest Guide

This guide explains how to use MQTT-based data ingest as an alternative to HTTP polling.

## Overview

WarDragon Analytics supports two methods for collecting data from WarDragon kits:

| Method | Description | Best For |
|--------|-------------|----------|
| **HTTP Polling** (default) | Analytics polls each kit's DragonSync API | Simple setup, kits behind NAT |
| **MQTT Push** (optional) | Kits push data to Analytics via MQTT broker | Real-time data, firewalled environments |

**Architecture with MQTT:**

```
WarDragon Kit                    Analytics Server
┌─────────────┐                  ┌───────────────────────────┐
│ DragonSync  │                  │ Mosquitto MQTT Broker     │
│             │   MQTT Publish   │ :1883                     │
│ MQTT Sink   │ ───────────────► │                           │
│             │                  │         │                 │
└─────────────┘                  │         ▼                 │
                                 │ MQTT Ingest Service       │
                                 │         │                 │
                                 │         ▼                 │
                                 │ TimescaleDB               │
                                 │         │                 │
                                 │         ▼                 │
                                 │ Web UI / Grafana          │
                                 └───────────────────────────┘
```

## Benefits of MQTT Ingest

- **Real-time data**: No polling delay - data arrives immediately
- **Auto-registration**: Kits appear automatically when they first publish
- **NAT/firewall friendly**: Kits initiate outbound connections
- **Lower overhead**: No HTTP request/response cycle
- **Scalable**: MQTT broker handles many concurrent connections efficiently

## Quick Start

### 1. Enable MQTT Services

Edit your `.env` file:

```bash
# Enable MQTT ingest
MQTT_INGEST_ENABLED=true
```

### 2. Start with MQTT Profile

```bash
# Start all services including MQTT
docker compose --profile mqtt up -d
```

This starts:
- **mosquitto**: MQTT broker on port 1883
- **mqtt-ingest**: Subscribes to MQTT topics and writes to database

### 3. Configure DragonSync on Each Kit

Edit `config.ini` on each WarDragon kit:

```ini
[MQTT]
mqtt_enabled = true
mqtt_host = YOUR_ANALYTICS_SERVER_IP
mqtt_port = 1883
mqtt_topic = wardragon/drones
mqtt_per_drone_enabled = true
mqtt_per_drone_base = wardragon/drone
mqtt_aircraft_enabled = true
mqtt_aircraft_topic = wardragon/aircraft
mqtt_signals_enabled = true
mqtt_signals_topic = wardragon/signals
```

Replace `YOUR_ANALYTICS_SERVER_IP` with the IP address or hostname of your Analytics server.

### 4. Verify Connection

Check that kits are sending data:

```bash
# View MQTT ingest logs
docker compose logs -f mqtt-ingest

# Subscribe to MQTT topics (for debugging)
docker exec -it wardragon-mosquitto mosquitto_sub -t 'wardragon/#' -v
```

Kits will auto-register in the Kit Manager with source type "MQTT".

## Configuration Options

### .env Settings

```bash
# Enable MQTT ingest service
MQTT_INGEST_ENABLED=true

# MQTT broker port (default: 1883)
MQTT_BROKER_PORT=1883

# Enable authentication (recommended for production)
MQTT_AUTH_ENABLED=false
MQTT_USERNAME=wardragon
MQTT_PASSWORD=your_secure_password

# Enable TLS encryption
MQTT_TLS_ENABLED=false

# Topic configuration (matches DragonSync defaults)
MQTT_TOPIC_DRONES=wardragon/drones
MQTT_TOPIC_DRONE_PREFIX=wardragon/drone/
MQTT_TOPIC_AIRCRAFT=wardragon/aircraft
MQTT_TOPIC_SIGNALS=wardragon/signals
MQTT_TOPIC_SYSTEM=wardragon/system
```

### Mosquitto Configuration

The default `mosquitto/mosquitto.conf` allows anonymous connections for easy setup.

For production, edit `mosquitto/mosquitto.conf`:

```conf
# Disable anonymous access
allow_anonymous false

# Enable password file authentication
password_file /mosquitto/config/passwd
```

Then create the password file:

```bash
# Generate password file
docker exec -it wardragon-mosquitto mosquitto_passwd -c /mosquitto/config/passwd wardragon

# Restart mosquitto
docker compose restart mosquitto
```

### TLS/SSL Configuration

For encrypted connections:

1. Generate or obtain certificates (self-signed for testing):
   ```bash
   mkdir -p mosquitto/certs
   openssl req -new -x509 -days 365 -nodes \
     -out mosquitto/certs/server.crt \
     -keyout mosquitto/certs/server.key
   ```

2. Update `mosquitto/mosquitto.conf`:
   ```conf
   listener 8883 0.0.0.0
   cafile /mosquitto/config/ca.crt
   certfile /mosquitto/config/server.crt
   keyfile /mosquitto/config/server.key
   require_certificate false
   ```

3. Update `.env`:
   ```bash
   MQTT_TLS_ENABLED=true
   MQTT_BROKER_PORT=8883
   ```

4. Configure DragonSync on kits to use TLS:
   ```ini
   mqtt_tls = true
   mqtt_port = 8883
   ```

## MQTT Topics

DragonSync publishes to these topics:

| Topic | Description | Format |
|-------|-------------|--------|
| `wardragon/drones` | Aggregate drone list | JSON array |
| `wardragon/drone/{id}` | Individual drone updates | JSON object |
| `wardragon/aircraft` | ADS-B aircraft data | JSON object |
| `wardragon/signals` | FPV signal detections | JSON object |
| `wardragon/system` | System health/status | JSON object |

### Example Message Formats

**Drone (wardragon/drones):**
```json
{
  "seen_by": "wardragon-abc123",
  "id": "drone-12345",
  "lat": 37.7749,
  "lon": -122.4194,
  "alt": 100.5,
  "speed": 15.2,
  "direction": 180,
  "rssi": -65,
  "pilot_lat": 37.7750,
  "pilot_lon": -122.4195,
  "rid_make": "DJI",
  "rid_model": "Mavic 3",
  "track_type": "drone"
}
```

**Aircraft (wardragon/aircraft):**
```json
{
  "seen_by": "wardragon-abc123",
  "icao": "A12345",
  "callsign": "UAL123",
  "lat": 37.8000,
  "lon": -122.4000,
  "alt": 35000,
  "speed": 450,
  "track": 90,
  "track_type": "aircraft"
}
```

**Signal (wardragon/signals):**
```json
{
  "seen_by": "wardragon-abc123",
  "freq_mhz": 5800,
  "power_dbm": -45,
  "bandwidth_hz": 20000000,
  "pal_conf": 0.95,
  "ntsc_conf": 0.05,
  "sensor_lat": 37.7749,
  "sensor_lon": -122.4194,
  "signal_type": "fpv"
}
```

## Kit Registration

MQTT kits auto-register when they first publish data:

- **New MQTT kits**: Registered with `source='mqtt'`
- **Existing HTTP kits**: Upgraded to `source='both'` if they also send MQTT
- **Kit Manager**: Shows source type indicator (📡 MQTT / 🌐 HTTP / 🔄 Both)

## Hybrid Mode

You can use both HTTP polling and MQTT simultaneously:

1. **HTTP polling** for kits in the same network
2. **MQTT push** for remote/firewalled kits

The collector service automatically skips MQTT-only kits (no api_url) and uses the freshest data when a kit sends via both methods.

## Troubleshooting

### MQTT Ingest Not Receiving Data

1. **Check MQTT broker is running:**
   ```bash
   docker compose ps mosquitto
   ```

2. **Verify kit can reach broker:**
   ```bash
   # On the kit
   mosquitto_pub -h ANALYTICS_SERVER_IP -t test -m "hello"
   ```

3. **Check broker logs:**
   ```bash
   docker compose logs mosquitto
   ```

4. **Verify topic subscriptions:**
   ```bash
   docker exec -it wardragon-mosquitto mosquitto_sub -t '#' -v
   ```

### Kits Not Auto-Registering

1. **Check kit_id in messages:**
   - Messages must include `seen_by` or `kit_id` field
   - DragonSync includes this automatically when MQTT is enabled

2. **Check ingest logs:**
   ```bash
   docker compose logs -f mqtt-ingest
   ```

### High Latency

1. **Check network connectivity:**
   ```bash
   ping ANALYTICS_SERVER_IP
   ```

2. **Monitor MQTT broker:**
   ```bash
   docker exec -it wardragon-mosquitto mosquitto_sub -t '$SYS/#' -v
   ```

3. **Increase QoS** (if reliability matters more than latency):
   - DragonSync uses QoS 0 by default (fire and forget)
   - Configure QoS 1 for guaranteed delivery

### Authentication Failed

1. **Verify credentials match:**
   - `.env` MQTT_USERNAME/PASSWORD must match DragonSync config
   - Password file must be regenerated after password change

2. **Check mosquitto logs:**
   ```bash
   docker compose logs mosquitto | grep -i auth
   ```

## Security Considerations

1. **Network isolation**: Run MQTT broker on a trusted network
2. **Authentication**: Enable username/password in production
3. **TLS encryption**: Use for connections over public networks
4. **Firewall**: Only expose port 1883/8883 to trusted IPs
5. **Rate limiting**: Mosquitto handles this automatically
6. **Topic ACLs**: Can restrict which topics each user can publish/subscribe to

## Performance

- **Mosquitto capacity**: 100,000+ concurrent connections
- **Message throughput**: 10,000+ messages/second
- **Latency**: Sub-millisecond on local network
- **Database impact**: Same as HTTP polling (uses same insert paths)

## Comparison: HTTP vs MQTT

| Aspect | HTTP Polling | MQTT Push |
|--------|--------------|-----------|
| **Setup complexity** | Simple (no broker needed) | Requires MQTT broker |
| **Real-time** | 5s polling delay | Immediate |
| **Firewall friendly** | Kit must accept inbound | Kit initiates outbound |
| **Auto-registration** | Manual kit add | Automatic |
| **Bandwidth** | HTTP overhead per poll | Efficient binary protocol |
| **Reliability** | Built-in HTTP retry | QoS levels (0, 1, 2) |
| **Debugging** | Easy (curl endpoints) | Need MQTT tools |

## Related Documentation

- [Architecture](architecture.md) - System design overview
- [Collector Service](collector-service.md) - HTTP polling details
- [Deployment Guide](deployment.md) - Production setup
