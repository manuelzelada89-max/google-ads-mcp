# Google Measurement MCP (GTM + GA4)

Standalone service for **Google Tag Manager (read/write/publish)** and
**Google Analytics 4 (read reports, list settings, create/delete key events)**.
Nothing modifies the original `google-ads-mcp` Python package or Cloud Run service.

## Safety

- All Google requests use **the current user's OAuth access token**, not an unrestricted service-account identity.
- Each write is two steps: `prepare_*` (read-only preview with signed 10-minute token), then `apply_*` after an **actual explicit approval from the user**. The assistant must not invent this approval.
- GTM update/delete checks Google's current `fingerprint` and refuses stale changes.
- GTM create refuses an existing same-name entity to reduce duplicates from retries.
- No changes go live until a separately confirmed `gtm_prepare_version(... operation="publish")` / `gtm_apply_version`.
- The service never allows deleting GTM containers, accounts or users.
- For safety, use a test workspace and inspect it before applying changes to production.

## Tools

**GTM**: list accounts/containers/workspaces; inspect entities; workspace status;
live version; version history; preview and apply tag/trigger/variable
create/update/delete; create/publish versions (separate approval).

**GA4**: list properties, data streams, custom dimensions and key events;
run GA4 Data API reports; preview and apply key-event create/delete. Editing
GA4 event *generation rules* is a different Admin API function, not included
in this initial tool set.

## Required APIs in the EXISTING GCP project

- Tag Manager API (`tagmanager.googleapis.com`)
- Google Analytics Admin API (`analyticsadmin.googleapis.com`)
- Google Analytics Data API (`analyticsdata.googleapis.com`)

Use the existing OAuth client if it is allowed to request these additional
scopes. Add the new service callback URL to its authorized redirect URIs;
existing authorization for Google Ads does NOT grant the new scopes.

## OAuth scopes

```text
openid
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/userinfo.profile
https://www.googleapis.com/auth/tagmanager.readonly
https://www.googleapis.com/auth/tagmanager.edit.containers
https://www.googleapis.com/auth/tagmanager.edit.containerversions
https://www.googleapis.com/auth/tagmanager.publish
https://www.googleapis.com/auth/analytics.readonly
https://www.googleapis.com/auth/analytics.edit
```

## Deploy from Cloud Shell

```bash
gcloud config set project neural-cairn-506003-t5
gcloud services enable tagmanager.googleapis.com analyticsadmin.googleapis.com analyticsdata.googleapis.com run.googleapis.com cloudbuild.googleapis.com
git clone https://github.com/manuelzelada89-max/google-ads-mcp.git
cd google-ads-mcp
git checkout feature/gtm-ga4-write-mcp-20261021
gcloud builds submit --config cloudbuild.measurement.yaml .
```

Create a new Cloud Run service **google-measurement-mcp**, region **us-central1**,
using the image:

```text
us-central1-docker.pkg.dev/neural-cairn-506003-t5/mcp-servers/google-measurement-mcp:latest
```

Use the **same Google OAuth client** as the existing Google Ads service if
appropriate, but **do not copy Google Ads API tokens or developer tokens**.
Configure environment variables/secrets in Cloud Run:

| Variable | Value |
| --- | --- |
| `MEASUREMENT_MCP_OAUTH_CLIENT_ID` | OAuth Web Application client ID |
| `MEASUREMENT_MCP_OAUTH_CLIENT_SECRET` | Secret Manager reference; never commit |
| `MEASUREMENT_MCP_BASE_URL` | New Cloud Run https URL, without /mcp |
| `MEASUREMENT_MCP_JWT_SIGNING_KEY` | New stable secret (>=32 chars), Secret Manager |
| `MEASUREMENT_MCP_APPROVAL_KEY` | New independent stable secret (>=32 chars), Secret Manager |
| `MEASUREMENT_MCP_STORAGE_TYPE` | `firestore` |
| `MEASUREMENT_MCP_FIRESTORE_PROJECT` | `neural-cairn-506003-t5` |
| `MEASUREMENT_MCP_FIRESTORE_DATABASE` | An existing accessible Firestore database (e.g. `(default)`) |

Cloud Run's service account needs Firestore read/write permissions for
OAuth session storage. Keep stable JWT/encryption keys across revisions.

Expose /mcp over HTTPS (Cloud Run's ingress allows unauthenticated HTTP
at the infrastructure layer only because FastMCP validates OAuth itself).
In Google's OAuth client, add the matching FastMCP Google callback URI.
**Verify callback from the server's advertised OAuth metadata** before adding
it, rather than guessing its path.

Then in ChatGPT: Settings > Plugins > Create/Connect custom MCP, add
`https://YOUR-CLOUD-RUN-URL/mcp`, authenticate with Google, and check tools
`gtm_list_accounts` and `ga4_list_properties`.

## No destructive deployment

This branch does not deploy anything, modify OAuth credentials, touch
live GTM tags, or alter the existing Ads service. It prepares code for
review and deployment using the existing GCP project.
