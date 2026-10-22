#!/usr/bin/env bash
# One-command Cloud Shell deployment. Only READS the existing Google Ads service.
# Creates a new, separate Cloud Run service and separate signing secrets.
set -euo pipefail
set +x
PROJECT="neural-cairn-506003-t5"
REGION="us-central1"
SOURCE_SERVICE="google-ads-mcp-manuel"
SERVICE="google-measurement-mcp"
IMAGE="us-central1-docker.pkg.dev/${PROJECT}/mcp-servers/${SERVICE}:latest"
BRANCH="feature/gtm-ga4-write-mcp-20261021"

command -v gcloud >/dev/null || { echo "Abre Google Cloud Shell primero."; exit 1; }
command -v jq >/dev/null || { echo "Instala jq en Cloud Shell."; exit 1; }
command -v openssl >/dev/null || { echo "Necesitas openssl."; exit 1; }

gcloud config set project "$PROJECT"
gcloud services enable tagmanager.googleapis.com analyticsadmin.googleapis.com \
    analyticsdata.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
    secretmanager.googleapis.com

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
gcloud run services describe "$SOURCE_SERVICE" --project "$PROJECT" \
    --region "$REGION" --format=json > "$tmp"

# Read only the exact allowlisted settings, never print any OAuth secrets.
get_value() {
    jq -r --arg n "$1" '
      ((.spec.template.spec.containers[0].env // .template.containers[0].env // [])
      | map(select(.name == $n)) | first // {}) | .value // empty
    ' "$tmp"
}
get_secret_ref() {
    jq -r --arg n "$1" '
      ((.spec.template.spec.containers[0].env // .template.containers[0].env // [])
      | map(select(.name == $n)) | first // {})
      | .valueFrom.secretKeyRef as $r
      | if $r == null then empty
        else ($r.name + ":" + ($r.key // "latest")) end
    ' "$tmp"
}

client_id="$(get_value GOOGLE_ADS_MCP_OAUTH_CLIENT_ID)"
client_id_secret="$(get_secret_ref GOOGLE_ADS_MCP_OAUTH_CLIENT_ID)"
client_secret="$(get_secret_ref GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET)"
firestore_database="$(get_value GOOGLE_ADS_MCP_STORAGE_FIRESTORE_DATABASE)"
firestore_database="${firestore_database:-(default)}"
sa="$(jq -r '.spec.template.spec.serviceAccountName // .template.serviceAccount // empty' "$tmp")"
if [[ -z "$sa" ]]; then
    number="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
    sa="${number}-compute@developer.gserviceaccount.com"
fi

if [[ -z "$client_id" && -z "$client_id_secret" ]]; then
    echo "No pude recuperar el OAuth Client ID del servicio existente."
    echo "Configura MEASUREMENT_MCP_OAUTH_CLIENT_ID en Cloud Run manualmente."
    exit 1
fi

# Prefer secret references. If the old OAuth secret was stored as plaintext,
# copy it to Secret Manager without echoing it or passing it in CLI flags.
if [[ -z "$client_secret" ]]; then
    raw="$(get_value GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET)"
    if [[ -z "$raw" ]]; then
        echo "No encontré GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET en $SOURCE_SERVICE."
        exit 1
    fi
    secret_name="google-measurement-oauth-secret"
    if ! gcloud secrets describe "$secret_name" --project "$PROJECT" >/dev/null 2>&1; then
        printf '%s' "$raw" | gcloud secrets create "$secret_name" \
          --project "$PROJECT" --replication-policy=automatic --data-file=- >/dev/null
    fi
    unset raw
    client_secret="${secret_name}:latest"
    gcloud secrets add-iam-policy-binding "$secret_name" --project "$PROJECT" \
       --member "serviceAccount:$sa" --role roles/secretmanager.secretAccessor >/dev/null
fi

# Distinct persistent keys for the new MCP; no reuse of Google Ads JWT state.
for secret_name in google-measurement-jwt google-measurement-approval; do
    if ! gcloud secrets describe "$secret_name" --project "$PROJECT" >/dev/null 2>&1; then
        openssl rand -hex 48 | gcloud secrets create "$secret_name" \
          --project "$PROJECT" --replication-policy=automatic --data-file=- >/dev/null
    fi
    gcloud secrets add-iam-policy-binding "$secret_name" --project "$PROJECT" \
       --member "serviceAccount:$sa" --role roles/secretmanager.secretAccessor >/dev/null
done

if [[ -n "$client_id_secret" ]]; then
    envs="MEASUREMENT_MCP_BASE_URL=https://setup.invalid,MEASUREMENT_MCP_STORAGE_TYPE=firestore,MEASUREMENT_MCP_FIRESTORE_PROJECT=$PROJECT,MEASUREMENT_MCP_FIRESTORE_DATABASE=$firestore_database"
    secrets="MEASUREMENT_MCP_OAUTH_CLIENT_ID=$client_id_secret,"
else
    envs="MEASUREMENT_MCP_OAUTH_CLIENT_ID=$client_id,MEASUREMENT_MCP_BASE_URL=https://setup.invalid,MEASUREMENT_MCP_STORAGE_TYPE=firestore,MEASUREMENT_MCP_FIRESTORE_PROJECT=$PROJECT,MEASUREMENT_MCP_FIRESTORE_DATABASE=$firestore_database"
    secrets=""
fi

secrets+="MEASUREMENT_MCP_OAUTH_CLIENT_SECRET=$client_secret,MEASUREMENT_MCP_JWT_SIGNING_KEY=google-measurement-jwt:latest,MEASUREMENT_MCP_APPROVAL_KEY=google-measurement-approval:latest"

echo "Compilando el MCP independiente GTM + GA4..."
gcloud builds submit --project "$PROJECT" --config cloudbuild.measurement.yaml .

echo "Creando el nuevo servicio Cloud Run (Google Ads queda intacto)..."
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" \
    --platform managed --image "$IMAGE" --allow-unauthenticated \
    --service-account "$sa" --min-instances=0 --max-instances=1 \
    --memory=512Mi --cpu=1 --set-env-vars "$envs" \
    --set-secrets "$secrets"

url="$(gcloud run services describe "$SERVICE" --project "$PROJECT" \
     --region "$REGION" --format='value(status.url)')"
[[ "$url" == https://* ]] || { echo "Cloud Run no devolvió una URL HTTPS válida."; exit 1; }

gcloud run services update "$SERVICE" --project "$PROJECT" --region "$REGION" \
    --update-env-vars "MEASUREMENT_MCP_BASE_URL=$url" >/dev/null

echo
echo "SERVICIO CREADO: $url"
echo "Google OAuth - Authorized redirect URI: $url/auth/callback"
echo "ChatGPT - MCP URL: $url/mcp"
echo
echo "PENDIENTE: agrega el redirect URI al mismo cliente OAuth existente."
echo "En la pantalla de consentimiento habilita los nuevos scopes de GTM y GA4."
echo "Después conéctalo en ChatGPT y prueba gtm_list_accounts."
