# WarDragon Analytics - Security Guide

> **⚠️ Development Status:** This project is under active development. While every effort is made to review code for security issues, exposing the web UI, API, or MQTT broker to the public internet without a VPN is not recommended.

## Security Checklist

### Pre-Deployment Security

- [ ] **Strong Passwords Generated**
  ```bash
  # Generate secure passwords
  openssl rand -base64 32  # DB_PASSWORD
  openssl rand -base64 32  # GRAFANA_PASSWORD
  openssl rand -base64 32  # GRAFANA_SECRET_KEY
  ```

- [ ] **.env File Protected**
  ```bash
  chmod 600 .env
  # Verify .env is in .gitignore
  grep -q "^\.env$" .gitignore && echo "OK" || echo "ADD .env to .gitignore!"
  ```

- [ ] **Volume Permissions Set**
  ```bash
  chmod 700 volumes/timescale-data
  chmod 700 volumes/grafana-data
  chown -R 472:472 volumes/grafana-data  # Grafana user
  ```

- [ ] **CORS Origins Configured**
  - In production, set `CORS_ORIGINS` to specific domains
  - Never use `*` in production

- [ ] **Firewall Configured**
  ```bash
  # Only allow necessary ports
  sudo ufw status
  # Close direct access to TimescaleDB (already bound to localhost)
  # Use reverse proxy for web/grafana with SSL
  ```

### Network Security

- [ ] **TimescaleDB Not Exposed**
  - Verify port binding: `127.0.0.1:5432:5432` (localhost only)
  - No external access to database

- [ ] **Reverse Proxy with SSL**
  - Use nginx/Traefik for SSL termination
  - Obtain Let's Encrypt certificates
  - Redirect HTTP to HTTPS

- [ ] **Network Isolation**
  - Services communicate via internal Docker network
  - Only web/grafana exposed through reverse proxy

### Application Security

- [ ] **Grafana Security**
  - Strong admin password set
  - Anonymous access disabled (`GF_AUTH_ANONYMOUS_ENABLED=false`)
  - Sign-up disabled (`GF_USERS_ALLOW_SIGN_UP=false`)
  - Session cookies secure and SameSite

- [ ] **Web API Security**
  - CORS properly configured
  - Input validation enabled
  - Rate limiting on login attempts (enabled with AUTH_ENABLED=true)
  - Optional authentication available (set AUTH_ENABLED=true in .env)

- [ ] **Collector Security**
  - Kits on trusted network or VPN
  - API endpoints validated
  - Retry logic prevents DoS

### MQTT Security (If Using MQTT Ingest)

- [ ] **MQTT Authentication Enabled**
  ```bash
  # Set in .env
  MQTT_AUTH_ENABLED=true
  MQTT_USERNAME=wardragon
  MQTT_PASSWORD=<strong-password>

  # Create password file in mosquitto
  docker exec -it wardragon-mosquitto mosquitto_passwd -c /mosquitto/config/passwd wardragon
  ```

- [ ] **MQTT TLS Encryption Enabled**
  - TLS recommended for any network beyond localhost
  - Especially important for data exchange across untrusted networks
  - Note: MQTT TLS is currently untested in production
  ```bash
  # Generate certificates
  ./scripts/generate-mqtt-certs.sh your-server-hostname

  # Enable in .env
  MQTT_TLS_ENABLED=true
  MQTT_TLS_PORT=8883

  # Uncomment TLS section in mosquitto/mosquitto.conf
  ```

- [ ] **MQTT Firewall Rules**
  ```bash
  # Only allow MQTT from trusted networks/VPN
  sudo ufw allow from 10.0.0.0/8 to any port 1883   # Internal only
  sudo ufw allow from 10.0.0.0/8 to any port 8883   # TLS port

  # OR restrict to specific kit IPs
  sudo ufw allow from 192.168.1.100 to any port 8883
  ```

- [ ] **MQTT Broker Isolation**
  - Do not expose MQTT ports (1883/8883) to public internet without VPN
  - Use TLS (port 8883) instead of unencrypted (port 1883) when possible
  - Consider client certificate authentication for high-security deployments

### DragonSync API Security (HTTP Polling Mode)

- [ ] **Kit API Protection**
  - WarDragon kits running DragonSync expose an API on port 8088
  - This API should NOT be exposed to public internet
  - Use VPN or private network for kit-to-analytics communication
  - MQTT push mode (kits initiate outbound) may be preferable to HTTP polling for firewalled environments

### Data Security

- [ ] **Database Encryption**
  - Volume encryption at rest (dm-crypt/LUKS)
  - SSL/TLS for database connections (future)

- [ ] **Backup Security**
  ```bash
  # Encrypted backups
  docker exec wardragon-timescaledb pg_dump -U wardragon wardragon | \
    gpg --encrypt --recipient your@email.com > backup.sql.gpg
  ```

- [ ] **Backup Storage**
  - Store backups off-site
  - Encrypt backup files
  - Test restore procedure regularly

- [ ] **Data Retention**
  - Implement retention policies (30 days configured)
  - Regularly purge old data
  - Archive important data before purging

### Access Control

- [ ] **User Accounts**
  - Run services as non-root user
  - Separate system user for WarDragon Analytics
  - Minimal privileges

- [ ] **SSH Security** (if remote deployment)
  - Disable password authentication
  - Use SSH keys only
  - Enable fail2ban
  - Change default SSH port

- [ ] **Sudo Access**
  - Limit sudo access
  - Audit sudo usage
  - Use `sudo -i` logs

### Monitoring and Auditing

- [ ] **Application Audit Logging**
  - Audit logs automatically track admin actions (kit management, exports, logins)
  - Logs written to application log file by default
  - Optional: Enable database audit storage with `AUDIT_TO_DATABASE=true`
  - Query audit logs via `/api/audit/logs` endpoint

- [ ] **Log Monitoring**
  ```bash
  # Monitor authentication attempts
  docker-compose logs grafana | grep -i "auth"
  docker-compose logs web | grep -i "audit"

  # Monitor database connections
  docker exec wardragon-timescaledb psql -U wardragon wardragon -c "
    SELECT * FROM pg_stat_activity WHERE datname = 'wardragon';"
  ```

- [ ] **Alerting Integration**
  - Configure webhook alerts for security events (optional)
  - Supports Slack, Discord, and generic HTTP webhooks
  - Set `ALERTING_ENABLED=true` and configure webhook URLs in .env

- [ ] **Failed Login Alerts**
  - Monitor Grafana failed logins
  - Web UI login attempts logged (when AUTH_ENABLED=true)
  - Rate limiting prevents brute force attacks

- [ ] **Resource Monitoring**
  - CPU/memory usage alerts
  - Disk space alerts
  - Database connection pool alerts

- [ ] **Security Updates**
  - Regularly update Docker images
  - Subscribe to security advisories
  - Patch vulnerabilities promptly

### Hardening Checklist

#### Operating System

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Enable automatic security updates
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades

# Install fail2ban
sudo apt install fail2ban
sudo systemctl enable fail2ban

# Configure firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
# MQTT ports - only if needed and preferably restricted to VPN/internal networks
# sudo ufw allow from 10.0.0.0/8 to any port 1883   # MQTT (unencrypted)
# sudo ufw allow from 10.0.0.0/8 to any port 8883   # MQTT TLS
sudo ufw enable
```

#### Docker Security

```bash
# Run Docker daemon with user namespace remapping
# Add to /etc/docker/daemon.json:
{
  "userns-remap": "default",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}

# Restart Docker
sudo systemctl restart docker

# Scan images for vulnerabilities
docker scan timescale/timescaledb:latest-pg15
docker scan grafana/grafana:latest
```

#### TimescaleDB Hardening

```sql
-- Connect to database
docker exec -it wardragon-timescaledb psql -U wardragon wardragon

-- Revoke public schema access
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO wardragon;

-- Enable SSL (future enhancement)
-- ALTER SYSTEM SET ssl = on;

-- Set strong password policy (pg_password_check extension)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Audit logging
ALTER SYSTEM SET log_connections = on;
ALTER SYSTEM SET log_disconnections = on;
ALTER SYSTEM SET log_duration = on;
ALTER SYSTEM SET log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h ';

-- Reload configuration
SELECT pg_reload_conf();
```

#### Grafana Hardening

```bash
# Disable Grafana user registration
GF_USERS_ALLOW_SIGN_UP=false

# Enforce strong passwords
GF_SECURITY_PASSWORD_MIN_LENGTH=12

# Enable cookie security
GF_SECURITY_COOKIE_SECURE=true
GF_SECURITY_COOKIE_SAMESITE=strict

# Disable Gravatar
GF_SECURITY_DISABLE_GRAVATAR=true

# Disable analytics
GF_ANALYTICS_REPORTING_ENABLED=false
GF_ANALYTICS_CHECK_FOR_UPDATES=false
```

### Incident Response

#### Suspected Breach

1. **Immediately**
   ```bash
   # Stop all services
   docker-compose down

   # Backup current state for forensics
   docker-compose logs > incident_logs_$(date +%Y%m%d_%H%M%S).txt

   # Backup database
   make backup
   ```

2. **Investigate**
   - Review logs for unauthorized access
   - Check database for suspicious queries
   - Review user activity in Grafana

3. **Remediate**
   - Change all passwords
   - Regenerate Grafana secret key
   - Review and update firewall rules
   - Patch vulnerabilities

4. **Restore**
   - Deploy with new credentials
   - Monitor closely for 48 hours

#### Data Loss

1. **Restore from backup**
   ```bash
   make restore BACKUP_FILE=backups/latest.sql.gz
   ```

2. **Verify data integrity**
   ```bash
   docker exec wardragon-timescaledb psql -U wardragon wardragon -c "
     SELECT
       'drones' as table,
       count(*) as records,
       max(time) as latest_record
     FROM drones
     UNION ALL
     SELECT
       'signals' as table,
       count(*) as records,
       max(time) as latest_record
     FROM signals;
   "
   ```

### Compliance Considerations

#### Data Privacy

- **PII Handling**: Drone operator IDs and pilot locations may be PII
- **Data Retention**: Implement retention policies per regulations
- **Access Logging**: Audit who accesses what data
- **Data Export**: Provide mechanisms for data export/deletion

#### Audit Requirements

- Log all authentication attempts
- Log all database queries (optional, verbose)
- Retain logs per compliance requirements
- Regular security audits

### Security Best Practices Summary

1. **Principle of Least Privilege**
   - Minimal permissions for all services
   - No root access unless necessary

2. **Defense in Depth**
   - Multiple layers of security
   - Network isolation
   - Application-level security

3. **Regular Updates**
   - Keep Docker images updated
   - Apply security patches promptly
   - Subscribe to security advisories

4. **Monitoring and Alerting**
   - Monitor logs continuously
   - Alert on suspicious activity
   - Regular security reviews

5. **Backup and Recovery**
   - Regular automated backups
   - Off-site backup storage
   - Tested restore procedures

6. **Documentation**
   - Document security procedures
   - Maintain incident response plan
   - Keep security contacts updated

### Vulnerability Reporting

If you discover a security vulnerability:

1. Open an issue at [GitHub Issues](https://github.com/alphafox02/WarDragonAnalytics/issues)
2. For sensitive vulnerabilities, use GitHub's private vulnerability reporting feature
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if known)

### Security Resources

- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [PostgreSQL Security](https://www.postgresql.org/docs/current/security.html)
- [Grafana Security](https://grafana.com/docs/grafana/latest/setup-grafana/configure-security/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

### Regular Security Maintenance

**Weekly:**
- Review access logs
- Check for failed login attempts
- Verify backup success

**Monthly:**
- Update Docker images
- Review user accounts
- Test backup restore
- Security patch review

**Quarterly:**
- Full security audit
- Penetration testing (if resources allow)
- Review and update security policies
- Update documentation

**Annually:**
- Comprehensive security assessment
- Review incident response plan
- Update security training
- Review compliance requirements

---

**Remember:** Security is an ongoing process, not a one-time task. Stay vigilant!
