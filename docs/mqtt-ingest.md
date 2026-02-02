# MQTT Ingest Guide

This guide explains how to use MQTT-based data ingest for real-time drone data collection.

## Overview

WarDragon Analytics supports two methods for collecting data from WarDragon kits:

| Method | Description | Best For |
|--------|-------------|----------|
| **MQTT Push** (default) | Kits push data to Analytics via MQTT broker | Real-time data, most deployments |
| **HTTP Polling** | Analytics polls each kit's DragonSync API | Kits behind strict NAT, legacy setups |

**Note**: As of January 2026, MQTT is enabled by default for easier onboarding and real-time data. See the [Security Hardening](#security-hardening-recommended) section below for production deployments.

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

MQTT services start automatically with the default `docker compose up -d` command.

This starts:
- **mosquitto**: MQTT broker on port 1883 (no authentication by default)
- **mqtt-ingest**: Subscribes to MQTT topics and writes to database

### 1. Start Analytics (MQTT included)

```bash
docker compose up -d
```

### 2. Configure DragonSync on Each Kit

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

---

## Security Hardening (Recommended)

By default, MQTT is configured for easy setup with no authentication. **For production deployments or networks with untrusted devices, you should enable authentication and/or TLS.**

### Why Secure MQTT?

Without authentication, anyone who can reach port 1883 can:
- Publish fake drone data to your database
- Subscribe to all drone tracking data
- Potentially disrupt your monitoring system

### Option 1: Enable Password Authentication (Recommended)

1. **Create password file:**
   ```bash
   # Generate password for user 'wardragon'
   docker exec -it wardragon-mosquitto mosquitto_passwd -c /mosquitto/config/passwd wardragon
   # Enter password when prompted
   ```

2. **Update mosquitto configuration:**
   Edit `mosquitto/mosquitto.conf`:
   ```conf
   # Change this line:
   allow_anonymous false

   # Uncomment this line:
   password_file /mosquitto/config/passwd
   ```

3. **Update .env with credentials:**
   ```bash
   MQTT_USERNAME=wardragon
   MQTT_PASSWORD=your_secure_password
   ```

4. **Update DragonSync on each kit** (`config.ini`):
   ```ini
   [MQTT]
   mqtt_username = wardragon
   mqtt_password = your_secure_password
   ```

5. **Restart services:**
   ```bash
   docker compose restart mosquitto mqtt-ingest
   ```

### Option 2: Firewall Restriction

If your kits are on a trusted network, restrict MQTT access by IP:

```bash
# Allow only specific kit IPs
sudo ufw allow from 192.168.1.100 to any port 1883
sudo ufw allow from 192.168.1.101 to any port 1883
# Deny all others
sudo ufw deny 1883
```

### Option 3: Enable TLS Encryption

See the [TLS/SSL Configuration](#tlsssl-configuration) section below for encrypted connections.

### Disabling MQTT

If you prefer HTTP polling only and don't need MQTT:

```bash
# Start without MQTT services
docker compose up -d --scale mosquitto=0 --scale mqtt-ingest=0
```

---

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

For encrypted MQTT connections over port 8883:

#### Quick Setup (Self-Signed Certificates)

1. Generate certificates using the provided script:
   ```bash
   ./scripts/generate-mqtt-certs.sh [your-server-hostname]
   ```

   This creates:
   - `mosquitto/certs/ca.crt` - CA certificate (copy to kits)
   - `mosquitto/certs/ca.key` - CA private key (keep secure)
   - `mosquitto/certs/server.crt` - Server certificate
   - `mosquitto/certs/server.key` - Server private key

2. Enable TLS in `mosquitto/mosquitto.conf` (uncomment the TLS section):
   ```conf
   # TLS listener on port 8883
   listener 8883 0.0.0.0
   protocol mqtt

   # Certificate paths
   cafile /mosquitto/certs/ca.crt
   certfile /mosquitto/certs/server.crt
   keyfile /mosquitto/certs/server.key

   # TLS version
   tls_version tlsv1.2

   # Don't require client certificates
   require_certificate false
   ```

3. Update `.env`:
   ```bash
   MQTT_TLS_ENABLED=true
   MQTT_TLS_PORT=8883
   ```

4. Restart MQTT services:
   ```bash
   docker compose restart mosquitto
   ```

5. Configure DragonSync on each kit:
   ```ini
   [MQTT]
   mqtt_enabled = true
   mqtt_host = YOUR_ANALYTICS_SERVER_IP
   mqtt_port = 8883
   mqtt_tls = true
   # Optional: path to CA cert for verification
   # mqtt_ca_cert = /home/wardragon/ca.crt
   ```

#### Production TLS Setup

For production environments, use certificates from a trusted CA:

1. **Option A: Let's Encrypt (Free)**
   ```bash
   # Install certbot
   sudo apt install certbot

   # Get certificate (requires port 80 open)
   sudo certbot certonly --standalone -d mqtt.yourdomain.com

   # Copy to mosquitto certs directory
   sudo cp /etc/letsencrypt/live/mqtt.yourdomain.com/fullchain.pem mosquitto/certs/server.crt
   sudo cp /etc/letsencrypt/live/mqtt.yourdomain.com/privkey.pem mosquitto/certs/server.key
   ```

2. **Option B: Commercial CA**
   - Purchase certificate from DigiCert, Comodo, etc.
   - Place `server.crt` and `server.key` in `mosquitto/certs/`

#### Verifying TLS Connection

Test the TLS connection:
```bash
# From Analytics server
docker exec -it wardragon-mosquitto mosquitto_sub \
  --cafile /mosquitto/certs/ca.crt \
  -h localhost -p 8883 \
  -t 'wardragon/#' -v

# From a kit (with openssl)
openssl s_client -connect YOUR_ANALYTICS_SERVER:8883 -CAfile ca.crt
```

## MQTT Topics

DragonSync publishes to these topics:

| Topic | Description | Format |
|-------|-------------|--------|
| `wardragon/drones` | Aggregate drone list | JSON object (single drone) |
| `wardragon/drone/{id}` | Individual drone updates | JSON object |
| `wardragon/aircraft` | ADS-B aircraft data | JSON object |
| `wardragon/signals` | FPV signal detections | JSON object |
| `wardragon/system/attrs` | System health/status | JSON object |

### Field Name Mapping (Important)

DragonSync's MQTT payload uses different field names than its HTTP API for Home Assistant compatibility. The `mqtt-ingest` service automatically translates these.

**System Health Fields (`wardragon/system/attrs`):**

| DragonSync MQTT Field | Database Column | Transformation |
|-----------------------|-----------------|----------------|
| `latitude` | `lat` | Direct copy |
| `longitude` | `lon` | Direct copy |
| `hae` | `alt` | Direct copy |
| `cpu_usage` | `cpu_percent` | Direct copy |
| `memory_total_mb`, `memory_available_mb` | `memory_percent` | Calculated: `(total-avail)/total * 100` |
| `disk_total_mb`, `disk_used_mb` | `disk_percent` | Calculated: `used/total * 100` |
| `uptime_s` | `uptime_hours` | Converted: `uptime_s / 3600` |
| `temperature` | `temp_cpu` | Direct copy |
| `pluto_temp` | `pluto_temp` | Direct copy |
| `zynq_temp` | `zynq_temp` | Direct copy |

**Why the transformation?** DragonSync sends raw values (MB, seconds) for Home Assistant displays like "2.1 GB free". WarDragonAnalytics stores percentages for simpler comparison across kits.

**Drone Fields (`wardragon/drones`):**
For drones, DragonSync sends **both** naming conventions (`lat` AND `latitude`), so no transformation needed.

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

The collector service automatically skips MQTT-only kits (those with no `api_url`).

### What If Both Are Enabled for One Kit?

If a kit is configured in `kits.yaml` (HTTP polling) AND has MQTT publishing enabled in DragonSync:

1. **Both work**: Data is accepted from both sources
2. **Kit marked as hybrid**: The kit's source is updated to `'both'`
3. **No data loss**: The database deduplicates based on (time, kit_id, drone_id)
4. **Slight overhead**: Redundant data collection - the kit is being polled AND pushing

**Recommendation**: For best efficiency, pick one method per kit:

- **Use MQTT only**: Don't add the kit to `kits.yaml` - let it auto-register via MQTT
- **Use HTTP only**: Don't enable MQTT in DragonSync's `config.ini`

If you accidentally enable both, nothing breaks, but you may notice:
- Higher database write volume
- Kit shown as "hybrid" in Kit Manager
- Slightly higher network traffic

To switch a hybrid kit to MQTT-only:
1. Remove the kit from `config/kits.yaml`
2. Delete the kit in Kit Manager (it will re-register as MQTT)
3. Or: Update the kit's `api_url` to empty in Kit Manager

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
