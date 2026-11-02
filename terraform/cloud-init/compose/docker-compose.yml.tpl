# NOTE: rendered via cloud-init by Terraform. Edits must happen in the .tpl.
# ADR-0032 §2: three services — app, litestream, caddy.
# ADR-0034 §1: litestream sidecar is the only writer to object storage.
# ADR-0036 §2: caddy image is a custom build pinned by digest.

name: budget-planner

services:
  app:
    image: ghcr.io/${github_owner}/budget-planner:${app_image_tag}
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
      BUDGET_PLANNER_ADMIN_EMAIL: "${admin_email}"
      BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD: "${admin_initial_password}"
      TZ: "Europe/Warsaw"
    volumes:
      - /data:/data:rw
    networks:
      - edge
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2).status==200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    stop_grace_period: 10s
    depends_on:
      litestream:
        condition: service_started

  litestream:
    image: litestream/litestream:0.3
    container_name: budget-planner-litestream
    restart: unless-stopped
    command: ["replicate", "-config", "/etc/litestream.yml"]
    environment:
      SCW_ACCESS_KEY: "${scw_access_key}"
      SCW_SECRET_KEY: "${scw_secret_key}"
    volumes:
      - /data:/data:rw
      - /etc/budget-planner/litestream.yml:/etc/litestream.yml:ro
    networks:
      - edge
    stop_grace_period: 30s

  caddy:
    image: caddy:2.8
    container_name: budget-planner-caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - /etc/budget-planner/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config
      - /var/log/caddy:/var/log/caddy
    networks:
      - edge
    depends_on:
      app:
        condition: service_started
    stop_grace_period: 15s

networks:
  edge:
    driver: bridge

volumes:
  caddy-data:
    driver: local
  caddy-config:
    driver: local
