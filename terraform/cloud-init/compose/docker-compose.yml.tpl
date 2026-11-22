# NOTE: rendered by Terraform into bp-config; the host agent writes it (ADR-0111). Edit the .tpl.
# ADR-0032 §2: three services — app, litestream, caddy.
# ADR-0034 §1: litestream sidecar is the only writer to object storage.
# ADR-0036 §2: caddy image is a custom build pinned by digest.

name: budget-planner

services:
  app:
    # ADR-0111: repo:tag@sha256:digest; the agent cosign-verifies it before pulling.
    image: ${app_image}
    container_name: budget-planner-app
    restart: unless-stopped
    user: "10001:10001"
    read_only: true
    tmpfs:
      - /tmp:size=64m
    environment:
      BUDGET_ENV: "production"
      BUDGET_DATABASE_URL: "sqlite:////data/budget.db"
      BUDGET_COOKIE_SECRET: "${cookie_secret}"
      BUDGET_TRUSTED_HOSTS: "${trusted_hosts}"
      # T-D135 / ADR-0067 §1: WebAuthn RP = the public browser hostname.
      BUDGET_WEBAUTHN_RP_ID: "${hostname}"
      BUDGET_WEBAUTHN_ORIGIN: "https://${hostname}"
      BUDGET_PLANNER_ADMIN_EMAIL: "${admin_email}"
      BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD: "${admin_initial_password}"
      BUDGET_BACKUP_MAX_AGE_DAYS: "${backup_max_age_days}"
      # T-D144 / ADR-0119: freshness file written by litestream-probe.
      BUDGET_REPLICATION_STATUS_FILE: "/replication/status.json"
      TZ: "Europe/Warsaw"
      BUDGET_FX_REFRESH_ENABLED: "true"
      # ADR-0133: trust X-Forwarded-For only from the edge bridge gateway, the
      # address the app sees for Caddy's loopback connection (never "*").
      FORWARDED_ALLOW_IPS: "172.28.0.1"
    volumes:
      - /data:/data:rw
      - /var/lib/budget-planner/replication:/replication:ro
    networks:
      - edge
    # ADR-0133: Caddy runs on the host network (real client address), so the app
    # is published on host loopback only; no public or tailnet exposure.
    ports:
      - "127.0.0.1:8000:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2).status==200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    stop_grace_period: 10s
    # ADR-0071: the image entrypoint applies pending migrations before
    # uvicorn starts; litestream-restore must finish first so a fresh /data
    # is restored from the replica rather than initialised empty.
    depends_on:
      litestream-restore:
        condition: service_completed_successfully
      litestream:
        condition: service_started

  # ADR-0071 §3 / ADR-0127: one-shot restore-before-start. No-op when
  # /data/budget.db exists; fails when it is missing and the replica is empty
  # (unless allow_empty_db). Writes /data/restore-report.json. Litestream runs
  # as root, so the script hands the files back to the app uid (10001).
  litestream-restore:
    image: litestream/litestream:0.3.14@sha256:c5a1e1b01916b3a110f6600820ef176d048d9b9c2411ef0a680de0caa68934a5
    container_name: budget-planner-litestream-restore
    restart: "no"
    entrypoint: ["/bin/sh", "/etc/litestream-restore.sh"]
    environment:
      SCW_ACCESS_KEY: "${scw_access_key}"
      SCW_SECRET_KEY: "${scw_secret_key}"
      LITESTREAM_ALLOW_EMPTY_DB: "${allow_empty_db}"
    volumes:
      - /data:/data:rw
      - /etc/budget-planner/litestream-restore.sh:/etc/litestream-restore.sh:ro
      - /etc/budget-planner/litestream-restore.yml:/etc/litestream.yml:ro
      - /etc/budget-planner/litestream-age.key:/run/litestream-age.key:ro
    networks:
      - edge

  litestream:
    image: litestream/litestream:0.3.14@sha256:c5a1e1b01916b3a110f6600820ef176d048d9b9c2411ef0a680de0caa68934a5
    container_name: budget-planner-litestream
    restart: unless-stopped
    # T-D136 / ADR-0114: exports the age identity and forces one new generation per host.
    entrypoint: ["/bin/sh", "/etc/litestream-entrypoint.sh"]
    command: ["replicate", "-config", "/etc/litestream.yml"]
    environment:
      SCW_ACCESS_KEY: "${scw_access_key}"
      SCW_SECRET_KEY: "${scw_secret_key}"
    volumes:
      - /data:/data:rw
      - /etc/budget-planner/litestream.yml:/etc/litestream.yml:ro
      - /etc/budget-planner/litestream-entrypoint.sh:/etc/litestream-entrypoint.sh:ro
      - /etc/budget-planner/litestream-age.key:/run/litestream-age.key:ro
    networks:
      - edge
    stop_grace_period: 30s
    depends_on:
      litestream-restore:
        condition: service_completed_successfully

  # T-D144 / ADR-0119: lists the replica every 5 min and writes the freshness
  # status file the app serves at /health/replication. /data is mounted
  # read-only because `litestream generations` stats the DB file.
  litestream-probe:
    image: litestream/litestream:0.3.14@sha256:c5a1e1b01916b3a110f6600820ef176d048d9b9c2411ef0a680de0caa68934a5
    container_name: budget-planner-litestream-probe
    restart: unless-stopped
    entrypoint: ["/bin/sh", "/etc/litestream-replication-probe.sh"]
    environment:
      SCW_ACCESS_KEY: "${scw_access_key}"
      SCW_SECRET_KEY: "${scw_secret_key}"
    volumes:
      - /data:/data:ro
      - /etc/budget-planner/litestream.yml:/etc/litestream.yml:ro
      - /etc/budget-planner/litestream-replication-probe.sh:/etc/litestream-replication-probe.sh:ro
      - /etc/budget-planner/litestream-age.key:/run/litestream-age.key:ro
      - /var/lib/budget-planner/replication:/status:rw
    networks:
      - edge
    depends_on:
      litestream-restore:
        condition: service_completed_successfully

  caddy:
    image: caddy:2.8@sha256:226d1f059b75399fe19182893c7184591c07b97afc8dfcf44eeb80c9a77a530f
    container_name: budget-planner-caddy
    restart: unless-stopped
    # ADR-0133: host networking keeps the real client source address (H4-01).
    # `ports:` is meaningless here; Caddy binds 80/443 on the host directly.
    network_mode: "host"
    volumes:
      - /etc/budget-planner/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config
      - /var/log/caddy:/var/log/caddy
      # ADR-0111: host agent status.json, served at /.well-known/bp-deploy-status.json.
      - /var/lib/budget-planner/status:/srv/bp-status:ro
%{~ if tailnet_only }
      # ADR-0101: certificate for the *.ts.net name comes from the host tailscaled.
      # The directory (not the socket file) is mounted so a tailscaled restart
      # does not leave a stale bind mount. Caddy runs as root, which tailscaled
      # accepts for cert requests; a non-root Caddy would need TS_PERMIT_CERT_UID.
      - /var/run/tailscale:/var/run/tailscale
%{~ endif }
    depends_on:
      app:
        condition: service_started
    stop_grace_period: 15s

networks:
  edge:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/24
          gateway: 172.28.0.1

volumes:
  caddy-data:
    driver: local
  caddy-config:
    driver: local
