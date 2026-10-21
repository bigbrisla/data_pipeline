#!/usr/bin/env bash
set -euo pipefail

set -a
source .env
set +a

REGION=europe-west1
SA_NAME=pipeline-runner
SA=${SA_NAME}@${GCP_PROJECT}.iam.gserviceaccount.com
ENV_VARS="GCP_PROJECT=${GCP_PROJECT},GCS_BUCKET=${GCS_BUCKET},BUDGET_SHEET_ID=${BUDGET_SHEET_ID},BUDGET_SHEET_GID=${BUDGET_SHEET_GID},META_MOCK_SHEET_ID=${META_MOCK_SHEET_ID},META_MOCK_SHEET_GID=${META_MOCK_SHEET_GID}"

gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com \
  --project "$GCP_PROJECT"

gcloud iam service-accounts create "$SA_NAME" --project "$GCP_PROJECT" || true

# permessi minimi: scrivere su BigQuery e sul bucket, niente di più
for role in roles/bigquery.dataEditor roles/bigquery.jobUser roles/storage.objectAdmin; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
    --member "serviceAccount:$SA" --role "$role" --condition=None --quiet >/dev/null
done

deploy_job() {
  gcloud run jobs deploy "$1" --source . --region "$REGION" --project "$GCP_PROJECT" \
    --service-account "$SA" --set-env-vars "$ENV_VARS" --max-retries 2 --task-timeout 30m \
    --args "$2"
}

schedule_job() {
  gcloud run jobs add-iam-policy-binding "$1" --region "$REGION" --project "$GCP_PROJECT" \
    --member "serviceAccount:$SA" --role roles/run.invoker --quiet >/dev/null
  gcloud scheduler jobs create http "$1-daily" --location "$REGION" --project "$GCP_PROJECT" \
    --schedule "$2" --time-zone "Europe/Rome" --http-method POST \
    --uri "https://run.googleapis.com/v2/projects/${GCP_PROJECT}/locations/${REGION}/jobs/$1:run" \
    --oauth-service-account-email "$SA" || true
}

deploy_job budget-sheet pipeline.sheets
deploy_job meta-insights pipeline.meta

schedule_job budget-sheet "0 6 * * *"
schedule_job meta-insights "30 6 * * *"
