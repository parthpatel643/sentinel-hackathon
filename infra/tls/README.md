# infra/tls — local mTLS PKI (generated, never committed)

Nothing in this directory is committed (see `.gitignore`) — every
developer and CI run generates their own throwaway CA + certs.

Generate everything with:

```bash
./scripts/generate_mtls_certs.sh [client-name]
```

This produces:
- `ca.crt` / `ca.key` — the local development Certificate Authority.
- `server.crt` / `server.key` — the edge-gateway (nginx) server identity,
  `CN=edge-gateway.sentinel.local`.
- `client-<name>.crt` / `client-<name>.key` — one edge-node client
  identity (default name: `edge-node-01`). Run the script again with a
  different name to mint additional edge-node client certs.

See [docs/08-SECURITY-HARDENING.md](../../docs/08-SECURITY-HARDENING.md)
for what this PKI is used for (mutual TLS between edge nodes and core,
terminated at `infra/compose/edge_gateway/`).
