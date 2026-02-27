#!/bin/bash
# Run this ONCE on your host to generate a self-signed cert for LAN use.
# The cert covers localhost + your machine's LAN IP.

set -e
mkdir -p certs

# Detect LAN IP (works on Linux/Mac)
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || ipconfig getifaddr en0 2>/dev/null || echo "192.168.1.1")
echo "Generating cert for: localhost, 127.0.0.1, $LAN_IP"

openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
  -keyout certs/key.pem \
  -out    certs/cert.pem \
  -subj   "/CN=firewatch-local" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:${LAN_IP}"

echo ""
echo "✅ Certs written to ./certs/cert.pem and ./certs/key.pem"
echo "   Import cert.pem into your browser/OS trust store to avoid the warning."