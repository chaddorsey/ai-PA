# Gmail Watch Service - GCP Setup Guide

This guide walks through setting up Google Cloud Pub/Sub for Gmail push notifications.

## Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- Gmail API already enabled (from gmail-mcp-server setup)
- Existing OAuth credentials from gmail-mcp-server

## Step 1: Set Project ID

```bash
export PROJECT_ID="your-gcp-project-id"
gcloud config set project $PROJECT_ID
```

## Step 2: Enable Pub/Sub API

```bash
gcloud services enable pubsub.googleapis.com
```

## Step 3: Create Pub/Sub Topic

```bash
gcloud pubsub topics create gmail-watch
```

## Step 4: Create Pull Subscription

```bash
gcloud pubsub subscriptions create gmail-watch-pull \
  --topic=gmail-watch \
  --ack-deadline=60 \
  --message-retention-duration=1d
```

## Step 5: Grant Gmail Publish Permission

Gmail needs permission to publish to your topic:

```bash
gcloud pubsub topics add-iam-policy-binding gmail-watch \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

## Step 6: Create Service Account for Pull

Create a service account for the watch service to pull messages:

```bash
gcloud iam service-accounts create gmail-watch-service \
  --display-name="Gmail Watch Service"

gcloud pubsub subscriptions add-iam-policy-binding gmail-watch-pull \
  --member="serviceAccount:gmail-watch-service@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"

gcloud iam service-accounts keys create gmail-watch-service/credentials/service-account.json \
  --iam-account=gmail-watch-service@${PROJECT_ID}.iam.gserviceaccount.com
```

## Step 7: Copy Gmail OAuth Credentials

The watch service needs the same OAuth credentials as gmail-mcp-server:

```bash
cp ~/.gmail-mcp/credentials.json gmail-watch-service/credentials/
```

## Step 8: Create Gmail "Watching" Label

Create the label in Gmail (can also be done automatically by the service):

1. Open Gmail
2. Go to Settings > Labels
3. Create new label named "Watching"

## Step 9: Create Gmail Filter for BCC

1. Open Gmail
2. Go to Settings > Filters
3. Create new filter:
   - To: `watch@yourdomain.com` (or `yourmail+watch@gmail.com`)
   - Action: Apply label "Watching"

## Step 10: Update Environment Variables

Add these to your `.env` file:

```bash
GCP_PROJECT_ID=your-gcp-project-id
EMAIL_AGENT_ID=agent-b4928949-8012-4436-a3c7-a9e510785147
```

## Step 11: Initialize Database Schema

```bash
cd gmail-watch-service
poetry run python scripts/init_db.py
```

## Step 12: Start the Service

```bash
docker-compose up -d gmail-watch-service
docker-compose logs -f gmail-watch-service
```

## Verification

Check service health:
```bash
curl http://localhost:8000/health
```

Check watch status:
```bash
curl http://localhost:8000/v1/status
```

## Troubleshooting

### "Permission denied" on Pub/Sub
Ensure the Gmail push service account has publisher access to your topic.

### "Invalid credentials"
Check that both `credentials.json` (OAuth) and `service-account.json` (Pub/Sub) exist in the credentials directory.

### "Watch subscription expired"
The service auto-renews watches, but you can manually renew:
```bash
curl -X POST http://localhost:8000/v1/admin/renew-watch
```
