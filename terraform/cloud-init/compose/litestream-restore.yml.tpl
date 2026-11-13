# NOTE: rendered via cloud-init by Terraform. Edits must happen in the .tpl.
# T-D56 / ADR-0078 §3: restore-only Litestream config (never used to replicate).
# $LITESTREAM_AGE_IDENTITY is exported by the litestream-restore service from
# /etc/budget-planner/litestream-age.key (0600 root) before litestream starts.

dbs:
  - path: /data/budget.db
    replicas:
      - type: s3
        endpoint: ${bucket_endpoint}
        region: ${bucket_region}
        bucket: ${bucket_name}
        path: db
        access-key-id: $${SCW_ACCESS_KEY}
        secret-access-key: $${SCW_SECRET_KEY}
        age:
          identities:
            - $${LITESTREAM_AGE_IDENTITY}
