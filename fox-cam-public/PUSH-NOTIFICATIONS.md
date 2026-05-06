# Push notifications (Web Push)

Our Foxes uses standards-based Web Push (RFC 8030) with VAPID
authentication (RFC 8292) instead of the previous ntfy.sh single-topic
fan-out. Every subscriber gets per-user, per-device delivery with
granular per-event-type preferences.

## Architecture

```
                   [ remix like POST ]            [ new Frigate event ]
                            ↓                              ↓
                  curator: notif_create              curator: curator.py
                            ↓                              ↓
                       web_push.send_to_user        web_push.broadcast_kind
                            ↓                              ↓
                   pywebpush (encrypt + sign)
                            ↓
                   browser push service (Apple/FCM/Mozilla)
                            ↓
                  service worker `push` handler
                            ↓
                  showNotification(title, options)
```

- **Subscriptions + preferences** live in the curator's SQLite DB
  (`push_subscriptions`, `push_preferences` tables).
- **fox-cam-public** is just an authed proxy; CF Access supplies the
  email header so the client can't spoof a different user's owner.
- **VAPID keypair** is shared between curator (signs JWTs, sends pushes)
  and the client (subscribes with the public half). fox-cam-public
  never sees the private key.

## One-time setup

1. Generate a VAPID keypair:
   ```bash
   PATH="/Volumes/main-drive/ai-PA/frigate-curator/venv/bin:$PATH" \
     bash scripts/generate-vapid-keys.sh
   ```
2. Paste the three printed lines into:
   - `/Volumes/main-drive/ai-PA/.env` (top-level)
   - `~/Library/LaunchAgents/com.ai-pa.frigate-curator.plist`
     under `<key>EnvironmentVariables</key>`
3. Reload the curator:
   ```bash
   launchctl kickstart -k gui/$(id -u)/com.ai-pa.frigate-curator
   ```

Rotating the keypair invalidates every existing client subscription.

## Notification kinds

Defined in `frigate_curator/db.py` under `PUSH_KIND_DEFAULTS`. Adding
a new kind is one line — the per-(email, kind) preferences table is
freeform on `kind`, so no migration is needed.

| Kind             | Default | Triggered by                                    |
|------------------|---------|-------------------------------------------------|
| `remix_like`     | on      | someone likes a remix you created               |
| `new_highlight`  | on      | curator detects a new fox-likely event          |

## iOS PWA requirement

iOS Safari supports Web Push only for installed PWAs (16.4+). The
client detects `navigator.standalone` / `display-mode: standalone`
and shows an "Add to Home Screen first" hint when needed; the
permission prompt fires inside the synchronous click handler so iOS
treats it as a user gesture.

## Endpoints

Curator:
- `GET  /push/vapid-public-key`
- `POST /push/subscriptions`
- `DELETE /push/subscriptions?endpoint=...`
- `GET  /push/subscriptions?email=...`
- `GET  /push/preferences?email=...`
- `POST /push/preferences`
- `POST /push/test?email=...`

fox-cam-public mirrors all of the above under `/api/push/*` (authed
via CF Access — owner email is server-injected, not client-supplied).

## Testing

From a logged-in browser with notifications enabled, click "Send test
push" in the profile popover → notification banner should appear in a
couple of seconds. To send from CLI:

```bash
curl -X POST 'http://127.0.0.1:5141/push/test?email=cdorsey@concord.org'
```

## Cleanup

Subscriptions auto-prune on 404/410 from the push service (browsers
return 410 Gone when the user uninstalls the PWA or resets push
permissions). No manual maintenance needed.
