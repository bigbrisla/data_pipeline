#!/usr/bin/env bash
set -euo pipefail

set -a
source .env
set +a

REGION=europe-west1
SA_NAME=pipeline-runner
SA=${SA_NAME}@${GCP_PROJECT}.iam.gserviceaccount.com
ENV_VARS="GCP_PROJECT=${GCP_PROJECT},GCS_BUCKET=${GCS_BUCKET},BUDGET_SHEET_ID=${BUDGET_SHEET_ID},BUDGET_SHEET_GID=${BUDGET_SHEET_GID},META_MOCK_SHEET_ID=${META_MOCK_SHEET_ID},META_MOCK_SHEET_GID=${META_MOCK_SHEET_GID}"

IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT}/pipeline/pipeline:latest

gcloud services enable run.googleapis.com cloudscheduler.googleapis.com artifactregistry.googleapis.com \
  --project "$GCP_PROJECT"

gcloud artifacts repositories create pipeline --repository-format docker --location "$REGION" \
  --project "$GCP_PROJECT" || true
gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin "https://${REGION}-docker.pkg.dev"
# Cloud Run gira su amd64, anche se il Mac è arm64
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"

gcloud iam service-accounts create "$SA_NAME" --project "$GCP_PROJECT" || true

# permessi minimi: scrivere su BigQuery e sul bucket, niente di più
for role in roles/bigquery.dataEditor roles/bigquery.jobUser roles/storage.objectAdmin; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
    --member "serviceAccount:$SA" --role "$role" --condition=None --quiet >/dev/null
done

deploy_job() {
  gcloud run jobs deploy "$1" --image "$IMAGE" --region "$REGION" --project "$GCP_PROJECT" \
    --service-account "$SA" --set-env-vars "$ENV_VARS" --max-retries 2 --task-timeout 30m \
    --command="python,-m,$2" --args=""
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
