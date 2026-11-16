# T-D59 — Log hygiene: redaction processor, query-string stripping, log retention

- **Phase**: 5 — Data-protection quick wins
- **Parallel-safe**: yes
- **Depends on**: T-D06, T-D23
- **References**: [ADR-0078](../../../adr/0078-v3-data-protection-quick-wins.md) §5

## Context

Structlog has no redaction step; Caddy's JSON access log records full URIs including query strings (ledger search `q`, filters). Logs are a side channel around every data-protection control.

## Deliverables

1. `logging.py`: `redact_sensitive` processor before the renderer. Deny-list (case-insensitive key match, prefix/suffix aware): `amount*`, `description`, `name`, `note*`, `memo`, `formula`, `q`, `search`, `email`, `password*`, `token*`, `secret*`, `*_json`. Values → `"[redacted]"`. Recurses into dicts/lists.
2. `terraform/cloud-init/compose/Caddyfile.tpl`: access log uses the `filter` encoder to drop the query string, e.g. `request>uri regexp "\?.*$" ""` (the `regexp` field filter; the per-key `query` filter cannot delete all params). Verify against the pinned Caddy version and record it in the handoff. Headers filter keeps `Cookie`/`Authorization` deleted (verify present).
3. cloud-init: logrotate for `/var/log/caddy/access.log` — daily, `rotate 14`, `compress`.
4. Test: app-level — run a ledger search with sentinel `ZZ_SENTINEL_42` through the TestClient with log capture; assert sentinel absent from every captured line. Unit test for the processor.

## Acceptance criteria

- Unit + integration tests above green.
- Prod-sim: `docker compose logs caddy` after a `?q=ZZ_SENTINEL_42` request shows no sentinel.

## Validation hook

```sh
just test tests/unit/test_logging_redaction.py tests/integration/web/test_no_values_in_logs.py
just test-prod-stack
```
