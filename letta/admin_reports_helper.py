"""Admin SDK Reports API helper for local-mode pulse tools.

Why this exists: `gws admin-reports` cannot use the dedicated admin-reports
credential's scopes (gws requests its own default scope set on refresh,
which excludes admin.reports.audit.readonly -> 403). The original drive/
email analytics design called the Admin Reports API via Python google-auth
with `~/.gmail-mcp/admin-reports.credentials.json`. This helper restores
that path using only the stdlib (urllib) so it needs no extra deps, and
exposes a `subprocess.run`-shaped result so call sites change by one line.

Host-side only; no Docker, no gws, no re-auth.
"""

import json
import os
import time
import types
import urllib.request
import urllib.parse

_ADMIN_CRED = os.path.expanduser(
    os.getenv("ADMIN_REPORTS_CREDENTIALS_FILE", "~/.gmail-mcp/admin-reports.credentials.json")
)
_REPORTS_BASE = "https://admin.googleapis.com/admin/reports/v1/activity/users"
_token_cache = {"access_token": None, "exp": 0.0}


def _get_token():
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["exp"] - 60:
        return _token_cache["access_token"]
    c = json.load(open(_ADMIN_CRED))
    data = urllib.parse.urlencode({
        "client_id": c["client_id"],
        "client_secret": c["client_secret"],
        "refresh_token": c["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    r = urllib.request.urlopen(
        urllib.request.Request(c.get("token_uri", "https://oauth2.googleapis.com/token"), data=data),
        timeout=30,
    )
    tok = json.loads(r.read())
    _token_cache["access_token"] = tok["access_token"]
    _token_cache["exp"] = now + float(tok.get("expires_in", 3600))
    return _token_cache["access_token"]


def admin_reports_activities_list(params):
    """Query Admin Reports activities. Returns the API dict {items, nextPageToken}.

    params keys: userKey, applicationName, startTime, endTime, maxResults, pageToken
    """
    user_key = params.get("userKey", "all")
    app = params.get("applicationName")
    query = {k: params[k] for k in ("startTime", "endTime", "maxResults", "pageToken")
             if params.get(k) is not None}
    url = (f"{_REPORTS_BASE}/{urllib.parse.quote(str(user_key))}"
           f"/applications/{urllib.parse.quote(str(app))}?{urllib.parse.urlencode(query)}")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + _get_token()})
    r = urllib.request.urlopen(req, timeout=60)
    return json.loads(r.read())


def gws_admin_reports_run(params):
    """Drop-in replacement for `subprocess.run(gws admin-reports ...)`.

    Returns an object with .returncode, .stdout (JSON str), .stderr so existing
    call-site error handling (checks returncode / parses stdout) works unchanged.
    """
    try:
        data = admin_reports_activities_list(params)
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr="")
    except Exception as e:  # noqa: BLE001 - surface any failure the same way gws did
        return types.SimpleNamespace(returncode=1, stdout="", stderr=str(e))
