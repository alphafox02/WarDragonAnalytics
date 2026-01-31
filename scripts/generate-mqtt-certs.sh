#!/bin/bash
# Generate self-signed certificates for MQTT TLS
# Usage: ./scripts/generate-mqtt-certs.sh [hostname]
#
# This script generates:
#   - CA certificate (ca.crt, ca.key)
#   - Server certificate (server.crt, server.key)
#
# For production, replace these with certificates from a trusted CA.

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CERT_DIR="$(dirname "$0")/../mosquitto/certs"
DAYS_VALID=365
KEY_SIZE=4096

# Get hostname (default to localhost)
HOSTNAME="${1:-localhost}"

echo -e "${GREEN}=== MQTT TLS Certificate Generator ===${NC}"
echo ""
echo "Hostname: $HOSTNAME"
echo "Certificate directory: $CERT_DIR"
echo "Validity: $DAYS_VALID days"
echo ""

# Create certs directory
mkdir -p "$CERT_DIR"

# Check if certificates already exist
if [ -f "$CERT_DIR/server.crt" ]; then
    echo -e "${YELLOW}WARNING: Certificates already exist in $CERT_DIR${NC}"
    read -p "Overwrite existing certificates? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

echo -e "${GREEN}[1/4] Generating CA private key...${NC}"
openssl genrsa -out "$CERT_DIR/ca.key" $KEY_SIZE 2>/dev/null

echo -e "${GREEN}[2/4] Generating CA certificate...${NC}"
openssl req -new -x509 -days $DAYS_VALID -key "$CERT_DIR/ca.key" \
    -out "$CERT_DIR/ca.crt" \
    -subj "/C=US/ST=Local/L=Local/O=WarDragon/OU=Analytics/CN=WarDragon CA" \
    2>/dev/null

echo -e "${GREEN}[3/4] Generating server private key and CSR...${NC}"
openssl genrsa -out "$CERT_DIR/server.key" $KEY_SIZE 2>/dev/null

# Create config for SAN (Subject Alternative Name)
cat > "$CERT_DIR/server.cnf" << EOF
[req]
default_bits = $KEY_SIZE
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = req_ext

[dn]
C = US
ST = Local
L = Local
O = WarDragon
OU = Analytics
CN = $HOSTNAME

[req_ext]
subjectAltName = @alt_names

[alt_names]
DNS.1 = $HOSTNAME
DNS.2 = localhost
DNS.3 = mosquitto
DNS.4 = wardragon-mosquitto
IP.1 = 127.0.0.1
IP.2 = 172.20.0.10
EOF

openssl req -new -key "$CERT_DIR/server.key" \
    -out "$CERT_DIR/server.csr" \
    -config "$CERT_DIR/server.cnf" \
    2>/dev/null

echo -e "${GREEN}[4/4] Signing server certificate with CA...${NC}"

# Create extensions file for signing
cat > "$CERT_DIR/server_ext.cnf" << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = $HOSTNAME
DNS.2 = localhost
DNS.3 = mosquitto
DNS.4 = wardragon-mosquitto
IP.1 = 127.0.0.1
IP.2 = 172.20.0.10
EOF

openssl x509 -req -in "$CERT_DIR/server.csr" \
    -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" \
    -CAcreateserial -out "$CERT_DIR/server.crt" \
    -days $DAYS_VALID \
    -extfile "$CERT_DIR/server_ext.cnf" \
    2>/dev/null

# Cleanup temporary files
rm -f "$CERT_DIR/server.csr" "$CERT_DIR/server.cnf" "$CERT_DIR/server_ext.cnf" "$CERT_DIR/ca.srl"

# Set permissions
chmod 600 "$CERT_DIR"/*.key
chmod 644 "$CERT_DIR"/*.crt

echo ""
echo -e "${GREEN}=== Certificates Generated Successfully ===${NC}"
echo ""
echo "Files created:"
echo "  $CERT_DIR/ca.crt      - CA certificate (copy to kits)"
echo "  $CERT_DIR/ca.key      - CA private key (keep secure)"
echo "  $CERT_DIR/server.crt  - Server certificate"
echo "  $CERT_DIR/server.key  - Server private key"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "1. Enable TLS in mosquitto.conf:"
echo "   Uncomment the TLS listener section"
echo ""
echo "2. Set MQTT_TLS_ENABLED=true in .env"
echo ""
echo "3. Restart MQTT services:"
echo "   docker compose --profile mqtt restart mosquitto"
echo ""
echo "4. Configure DragonSync on each kit:"
echo "   mqtt_tls = true"
echo "   mqtt_port = 8883"
echo ""
echo "5. Copy ca.crt to kits for certificate verification (optional):"
echo "   scp $CERT_DIR/ca.crt wardragon@<kit-ip>:/home/wardragon/"
echo ""
echo -e "${YELLOW}For production:${NC}"
echo "  Replace self-signed certs with certificates from a trusted CA"
echo "  (Let's Encrypt, DigiCert, etc.)"
echo ""
