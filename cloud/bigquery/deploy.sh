#!/bin/bash
# Deploy BigQuery telemetry infrastructure
# This script creates the dataset, events table, and views for Wrack telemetry

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"
DATASET="wrack_telemetry"
LOCATION="europe-west3"  # EU region for data residency
PARTITION_EXPIRATION_MS=7776000000  # 90 days in milliseconds

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMAS_DIR="${SCRIPT_DIR}/schemas"

echo "=================================================="
echo "  Wrack Telemetry - BigQuery Deployment"
echo "=================================================="
echo "Project:  ${PROJECT_ID}"
echo "Dataset:  ${DATASET}"
echo "Location: ${LOCATION}"
echo "=================================================="
echo ""

# Check if bq CLI is available
if ! command -v bq &> /dev/null; then
    echo "ERROR: 'bq' command not found. Please install Google Cloud SDK."
    echo "Visit: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Set the active project
echo "Setting active project to ${PROJECT_ID}..."
gcloud config set project "${PROJECT_ID}" 2>/dev/null || {
    echo "ERROR: Failed to set project. Check if project ${PROJECT_ID} exists."
    exit 1
}

# Create dataset
echo ""
echo "Creating dataset '${DATASET}'..."
bq mk \
  --dataset \
  --location="${LOCATION}" \
  --description="Telemetry data warehouse for Wrack robot system" \
  --default_table_expiration="${PARTITION_EXPIRATION_MS}" \
  "${PROJECT_ID}:${DATASET}" 2>/dev/null || echo "Dataset already exists, continuing..."

# Create events table
echo ""
echo "Creating events table..."
bq query \
  --use_legacy_sql=false \
  --project_id="${PROJECT_ID}" \
  < "${SCHEMAS_DIR}/events.sql"

if [ $? -eq 0 ]; then
    echo "✓ Events table created successfully"
else
    echo "✗ Failed to create events table"
    exit 1
fi

# Create views
echo ""
echo "Creating views..."
bq query \
  --use_legacy_sql=false \
  --project_id="${PROJECT_ID}" \
  < "${SCHEMAS_DIR}/views.sql"

if [ $? -eq 0 ]; then
    echo "✓ Views created successfully"
else
    echo "✗ Failed to create views"
    exit 1
fi

# Verify deployment
echo ""
echo "Verifying deployment..."
echo ""
echo "Dataset info:"
bq show "${PROJECT_ID}:${DATASET}"

echo ""
echo "Tables and views:"
bq ls "${PROJECT_ID}:${DATASET}"

echo ""
echo "=================================================="
echo "  Deployment completed successfully!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Run setup-iam.sh to create service account (PEN-155)"
echo "  2. Define event schemas in shared/telemetry-types/ (PEN-156)"
echo "  3. Test insertion with: bq query --use_legacy_sql=false"
echo ""
echo "Example query:"
echo "  SELECT * FROM \`${PROJECT_ID}.${DATASET}.events\`"
echo "  WHERE DATE(timestamp) = CURRENT_DATE()"
echo "  LIMIT 10"
echo ""
