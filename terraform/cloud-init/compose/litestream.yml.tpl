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
