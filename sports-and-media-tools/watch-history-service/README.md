# Watch History Polling Service

A unified service for polling streaming services for watch history and Continue Watching data.

## Overview

This service uses two approaches:

1. **API Polling** - For services with accessible internal APIs:
   - Max (HBO)
   - Hulu
   - Disney+
   - Apple TV+

2. **Browser Scraping** - For services with protected APIs:
   - Netflix (scrapes `/settings/viewed/{profileGUID}`)
   - Prime Video (scrapes `/gp/video/settings/watch-history`)

## Endpoints

### Health Check
```
GET /health
```

### Poll All Services
```
POST /poll
Body: {"username": "chad"}
```

### Poll Specific Service
```
POST /poll/<service>
Body: {"username": "chad"}
```
Services: `max`, `hulu`, `disney`, `apple`, `netflix`, `prime`

### Update Credentials
```
POST /credentials/<service>
Body: {
  "cookies": [...],
  "bearer_token": "...",  // for Disney+, Apple TV+
  "profile_guid": "...",  // for Netflix
  "profile_id": "..."     // for Disney+
}
```

### Check Credential Status
```
GET /credentials/<service>
```

## Credentials Format

### Netflix
```json
{
  "cookies": [
    {"name": "NetflixId", "value": "...", "domain": ".netflix.com"},
    {"name": "SecureNetflixId", "value": "...", "domain": ".netflix.com"}
  ],
  "profile_guid": "E3AOULSJTZD4ZLEVCCBR4WYU2Q"
}
```

### Prime Video
```json
{
  "cookies": [
    {"name": "at-main", "value": "Atza|...", "domain": ".amazon.com"},
    {"name": "sess-at-main", "value": "...", "domain": ".amazon.com"},
    {"name": "session-id", "value": "...", "domain": ".amazon.com"}
  ]
}
```

### Max (HBO)
```json
{
  "cookies": [
    {"name": "st", "value": "eyJ...", "domain": ".max.com"}
  ],
  "jwt_token": "eyJ..."
}
```

### Hulu
```json
{
  "cookies": [
    {"name": "_hulu_session", "value": "...", "domain": ".hulu.com"}
  ]
}
```

### Disney+
```json
{
  "bearer_token": "eyJ...",
  "profile_id": "63626081279ebe65eb50fb54"
}
```

### Apple TV+
```json
{
  "cookies": [
    {"name": "myacinfo", "value": "...", "domain": ".apple.com"},
    {"name": "media-user-token", "value": "...", "domain": ".apple.com"}
  ],
  "bearer_token": "eyJ...",
  "media_user_token": "AtbS0..."
}
```

## Usage with Letta

The sleeptime agent can use these Letta tools:

```python
# Poll all services
poll_watch_history()

# Poll specific service
poll_watch_history(service="netflix", username="chad")

# Check which services have credentials configured
check_credential_status()

# Update credentials for a service
update_streaming_credentials(
    service="netflix",
    cookies_json='[{"name": "NetflixId", "value": "..."}]',
    additional_params='{"profile_guid": "E3AOULSJTZD4ZLEVCCBR4WYU2Q"}'
)
```

## How to Get Credentials

### For all services:
1. Log into the service in your browser
2. Open DevTools (F12) → Application/Storage → Cookies
3. Export cookies using a browser extension (e.g., "EditThisCookie")
4. Save as JSON

### Additional notes:
- **Netflix**: Profile GUID is in the URL when you access settings
- **Disney+/Apple TV+**: Bearer tokens can be found in Network tab requests
- Credentials typically expire in 1-12 months depending on service

## Docker

```yaml
watch-history-service:
  build:
    context: ./sports-and-media-tools/watch-history-service
    dockerfile: Dockerfile
  volumes:
    - content-database-data:/app/data
    - watch-history-credentials:/app/credentials
  ports:
    - "5127:5127"
```

