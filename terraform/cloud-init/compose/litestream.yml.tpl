# NOTE: rendered via cloud-init by Terraform. Edits must happen in the .tpl.
# ADR-0034 §3: continuous WAL replication to Scaleway Object Storage.

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
        retention: 720h
        retention-check-interval: 24h
        snapshot-interval: 24h
        sync-interval: 10s
        # T-D56 / ADR-0078 §3: client-side age encryption (Litestream 0.3.x only).
        # The identity lives in /etc/budget-planner/litestream-age.key. T-D136 /
        # ADR-0114: replicate needs it too, because on every start Litestream
        # decrypts the last WAL segment to find its position. The entrypoint
        # (litestream-entrypoint.sh) exports it as $LITESTREAM_AGE_IDENTITY.
        # Lost identity = unrecoverable replica.
        age:
          recipients:
            - ${age_recipient}
          identities:
            - $${LITESTREAM_AGE_IDENTITY}
