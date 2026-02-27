FROM nginx:alpine

# Install openssl so we can generate certs at build time
RUN apk add --no-cache openssl

# Generate a self-signed cert valid for 10 years
# Covers localhost and any LAN IP (browsers still warn, just click "proceed")
RUN mkdir -p /etc/nginx/certs && \
    openssl req -x509 \
      -newkey rsa:2048 \
      -sha256 \
      -days 3650 \
      -nodes \
      -keyout /etc/nginx/certs/key.pem \
      -out    /etc/nginx/certs/cert.pem \
      -subj   "/CN=firewatch-local" \
      -addext "subjectAltName=DNS:localhost,DNS:*.local,IP:127.0.0.1"

COPY nginx.conf /etc/nginx/nginx.conf