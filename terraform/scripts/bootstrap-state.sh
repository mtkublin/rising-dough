#!/usr/bin/env bash
# Idempotent one-shot bootstrap of the Terraform remote-state bucket.
# ADR-0035 §4. Requires an operator Scaleway API key in SCW_ACCESS_KEY / SCW_SECRET_KEY.
#
#   ./terraform/scripts/bootstrap-state.sh
#
# Running twice is a no-op; the second run reports "already exists" and exits 0.

set -euo pipefail

BUCKET="${BUCKET:-budget-planner-tfstate-pl-waw}"
REGION="${REGION:-pl-waw}"
ENDPOINT="${ENDPOINT:-https://s3.${REGION}.scw.cloud}"

if [[ -z "${SCW_ACCESS_KEY:-}" || -z "${SCW_SECRET_KEY:-}" ]]; then
    echo "SCW_ACCESS_KEY and SCW_SECRET_KEY must be set in the environment." >&2
    exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
    echo "aws CLI is required (used in S3-compatible mode against Scaleway Object Storage)." >&2
    echo "Install via: brew install awscli" >&2
    exit 1
fi

export AWS_ACCESS_KEY_ID="${SCW_ACCESS_KEY}"
export AWS_SECRET_ACCESS_KEY="${SCW_SECRET_KEY}"
export AWS_DEFAULT_REGION="${REGION}"

# Check existence (idempotency guard).
if aws s3api head-bucket \
    --bucket "${BUCKET}" \
    --endpoint-url "${ENDPOINT}" \
    >/dev/null 2>&1; then
    echo "bucket ${BUCKET} already exists in ${REGION} — nothing to do"
    exit 0
fi

echo "creating bucket ${BUCKET} in ${REGION}..."
aws s3api create-bucket \
    --bucket "${BUCKET}" \
    --region "${REGION}" \
    --endpoint-url "${ENDPOINT}" \
    --create-bucket-configuration "LocationConstraint=${REGION}"

echo "enabling versioning..."
aws s3api put-bucket-versioning \
    --bucket "${BUCKET}" \
    --versioning-configuration Status=Enabled \
    --endpoint-url "${ENDPOINT}"

echo "blocking all public access..."
aws s3api put-public-access-block \
    --bucket "${BUCKET}" \
    --endpoint-url "${ENDPOINT}" \
    --public-access-block-configuration '{
        "BlockPublicAcls": true,
        "IgnorePublicAcls": true,
        "BlockPublicPolicy": true,
        "RestrictPublicBuckets": true
    }'

echo "done. bucket ${BUCKET} ready for terraform backend."
