let evtSource = null;

function fmt(n) { return n != null ? n.toLocaleString() : '-'; }
function fmtTime(s) {
  if (!s || s <= 0) return '-';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return h + 'h ' + m + 'm';
  return m + 'm';
}

function update(d) {
  const total = d.total || 0;
  const processed = (d.success || 0) + (d.skipped || 0) + (d.error || 0);
  const pct = total > 0 ? (processed / total * 100) : 0;

  // Status badge
  const badge = document.getElementById('statusBadge');
  badge.textContent = d.state || 'idle';
  badge.className = 'status-badge status-' + (d.state || 'idle');

  // Progress
  document.getElementById('progressFill').style.width = pct.toFixed(1) + '%';
  document.getElementById('progressText').textContent = fmt(processed) + ' / ' + fmt(total) + ' docs (' + pct.toFixed(1) + '%)';

  // Counts
  document.getElementById('cntOk').textContent = fmt(d.success) + ' ok';
  document.getElementById('cntSkip').textContent = fmt(d.skipped) + ' skip';
  document.getElementById('cntErr').textContent = fmt(d.error) + ' err';

  // Performance
  document.getElementById('rate').textContent = d.rate ? d.rate.toFixed(2) : '-';
  document.getElementById('eta').textContent = fmtTime(d.eta_seconds);
  document.getElementById('elapsed').textContent = fmtTime(d.elapsed);
  document.getElementById('cost').textContent = '$' + (d.cost_estimate || 0).toFixed(2);

  // Controls
  const state = d.state || 'idle';
  document.getElementById('btnStart').disabled = state === 'running';
  document.getElementById('btnPause').disabled = state !== 'running';
  document.getElementById('btnResume').disabled = state !== 'paused';

  // Neo4j stats
  if (d.neo4j) {
    const dl = document.getElementById('neo4jStats');
    dl.innerHTML = '';
    for (const [k, v] of Object.entries(d.neo4j)) {
      dl.innerHTML += '<dt>' + k + '</dt><dd>' + fmt(v) + '</dd>';
    }
  }

  // Store for offline
  try { localStorage.setItem('lastStatus', JSON.stringify(d)); } catch(e) {}
}

async function apiPost(action) {
  try {
    const r = await fetch('/api/' + action, { method: 'POST' });
    const d = await r.json();
    console.log(action, d);
    refresh();
  } catch(e) { console.error(action, e); }
}

async function refresh() {
  try {
    const r = await fetch('/api/status');
    update(await r.json());
  } catch(e) { console.error('status fetch failed', e); }

  try {
    const r = await fetch('/api/errors?limit=20');
    const errors = await r.json();
    const el = document.getElementById('errorList');
    document.getElementById('errCount').textContent = errors.length > 0 ? '(' + errors.length + ')' : '';
    if (errors.length === 0) {
      el.innerHTML = '<em style="color:var(--text-dim)">None</em>';
    } else {
      el.innerHTML = errors.map(function(e) {
        return '<div class="error-item"><div class="error-id">' + e.file_id.substring(0, 20) + '...</div><div class="error-msg">' + (e.error_message || 'unknown') + '</div></div>';
      }).join('');
    }
  } catch(e) {}
}

function connectSSE() {
  if (evtSource) evtSource.close();
  evtSource = new EventSource('/api/events');
  evtSource.addEventListener('progress', function(e) {
    try { update(JSON.parse(e.data)); } catch(err) {}
  });
  evtSource.onerror = function() {
    evtSource.close();
    evtSource = null;
    setTimeout(connectSSE, 5000);
  };
}

async function subscribePush() {
  try {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      alert('Push notifications not supported in this browser');
      return;
    }
    const reg = await navigator.serviceWorker.register('/sw.js');
    const keyResp = await fetch('/api/push/vapid-key');
    const keyData = await keyResp.json();

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(keyData.public_key)
    });

    await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sub.toJSON())
    });

    document.getElementById('notifyBtn').textContent = 'Notifications on';
    document.getElementById('notifyBtn').disabled = true;
  } catch(e) {
    console.error('Push subscribe failed', e);
    alert('Failed to enable notifications: ' + e.message);
  }
}

function urlBase64ToUint8Array(base64String) {
  var padding = '='.repeat((4 - base64String.length % 4) % 4);
  var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  var rawData = window.atob(base64);
  var outputArray = new Uint8Array(rawData.length);
  for (var i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

// Init
(function() {
  // Try offline data first
  try {
    var cached = localStorage.getItem('lastStatus');
    if (cached) update(JSON.parse(cached));
  } catch(e) {}

  refresh();
  connectSSE();
  setInterval(refresh, 30000); // Fallback polling every 30s for errors + neo4j
})();
