#!/usr/bin/env bash
# Generates the local mTLS PKI for edge-agent <-> core-api: a CA, a server
# cert for the edge-gateway (nginx) reverse proxy, and one client cert per
# edge node. Nothing here is committed (see .gitignore) — every developer
# and CI run generates their own throwaway PKI.
#
# docs/01-ARCHITECTURE.md / docs/07-DRIVER-SDK.md's sibling security doc
# explains why mTLS is terminated at a reverse proxy (nginx) rather than in
# core_api's own ASGI app: FastAPI/uvicorn has no standard way to hand a
# verified peer client certificate up to application code, so a gateway
# that *can* speak raw TLS (nginx) does the verification and forwards the
# result as a header core_api trusts only when paired with a shared secret
# (see edge_gateway/nginx.conf and core_api/security/mtls.py).
set -euo pipefail

cd "$(dirname "$0")/../infra/tls"

DAYS=825
CLIENT_NAME="${1:-edge-node-01}"

echo "==> Generating CA"
openssl genrsa -out ca.key 4096 2>/dev/null
openssl req -x509 -new -nodes -key ca.key -sha256 -days "$DAYS" \
  -subj "/O=Sentinel Platform/CN=Sentinel Dev CA" -out ca.crt 2>/dev/null

echo "==> Generating edge-gateway server cert (CN=edge-gateway.sentinel.local)"
openssl genrsa -out server.key 2048 2>/dev/null
openssl req -new -key server.key -subj "/O=Sentinel Platform/CN=edge-gateway.sentinel.local" \
  -out server.csr 2>/dev/null
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days "$DAYS" -sha256 \
  -extfile <(printf "subjectAltName=DNS:edge-gateway.sentinel.local,DNS:localhost,IP:127.0.0.1") \
  -out server.crt 2>/dev/null

echo "==> Generating edge client cert (CN=$CLIENT_NAME)"
openssl genrsa -out "client-${CLIENT_NAME}.key" 2048 2>/dev/null
openssl req -new -key "client-${CLIENT_NAME}.key" -subj "/O=Sentinel Platform/CN=${CLIENT_NAME}" \
  -out "client-${CLIENT_NAME}.csr" 2>/dev/null
openssl x509 -req -in "client-${CLIENT_NAME}.csr" -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days "$DAYS" -sha256 -out "client-${CLIENT_NAME}.crt" 2>/dev/null

rm -f server.csr "client-${CLIENT_NAME}.csr"

echo "==> Done. Generated in infra/tls/:"
ls -1 ./*.crt ./*.key
echo
echo "Start the gateway:   docker compose -f infra/compose/docker-compose.yml up -d edge-gateway"
echo "Test without a cert (must fail):"
echo "  curl -sk https://localhost:8443/health"
echo "Test with the client cert (must succeed):"
echo "  curl -sk --cert infra/tls/client-${CLIENT_NAME}.crt --key infra/tls/client-${CLIENT_NAME}.key https://localhost:8443/health"
