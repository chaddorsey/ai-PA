// Gmail Drafts & Follow-Ups Sidebar — view, edit, send, schedule, and discard

// Auto-inject CSRF on same-origin state-changing /api calls. drafts.js
// was written before ingress_guard landed and has 14 mutating fetches
// that would each need a header update; this wrapper fixes them all at
// once. Idempotent — skips if an X-CSRF-Token header is already set.
(function installCsrfFetchShim() {
  if (window.__paCsrfFetchShimInstalled) return;
  window.__paCsrfFetchShimInstalled = true;
  const originalFetch = window.fetch.bind(window);
  window.fetch = async function patchedFetch(input, init) {
    init = init || {};
    const method = (init.method || 'GET').toUpperCase();
    const mutating = method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS';
    if (!mutating) return originalFetch(input, init);

    // Only touch same-origin /api/ URLs. Leave everything else alone.
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const sameOrigin = url.startsWith('/') || url.startsWith(window.location.origin);
    if (!sameOrigin || !url.includes('/api/')) return originalFetch(input, init);

    const headers = new Headers(init.headers || {});
    if (!headers.has('X-CSRF-Token')) {
      const m = document.cookie.match(/(?:^|; )pa_csrf_cookie=([^;]*)/);
      const token = m ? decodeURIComponent(m[1]) : (window.__paCsrfToken || '');
      if (token) headers.set('X-CSRF-Token', token);
    }
    init.headers = headers;
    if (init.credentials === undefined) init.credentials = 'same-origin';
    return originalFetch(input, init);
  };
})();

class DraftsSidebar {
  constructor(taskSidebar) {
    this.taskSidebar = taskSidebar;
    this.drafts = [];
    this.pollInterval = null;
    this.draftList = document.getElementById('draft-list');
    this.pendingScheduleId = null;
    this.pendingScheduleSource = null;
    this.bindScheduleEvents();
  }

  // ── Polling ──

  startPolling() {
    this.stopPolling();
    this.pollInterval = setInterval(() => this.loadDrafts(), 30000);
  }

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }

  // ── Loading ──

  async loadDrafts() {
    try {
      this.draftList.classList.add('loading');
      const resp = await fetch('/api/drafts');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      this.drafts = data.drafts || [];
      this.updateBadge(this.drafts.length);
      this.renderDraftList();
    } catch (e) {
      this.draftList.innerHTML = `<div class="sidebar-error">Unable to load drafts<br><small>${this.escapeHtml(e.message)}</small></div>`;
    } finally {
      this.draftList.classList.remove('loading');
    }
  }

  updateBadge(count) {
    const badge = document.getElementById('sidebar-badge');
    const tabCount = document.getElementById('drafts-tab-count');
    tabCount.textContent = count > 0 ? count : '';
    if (this.taskSidebar.activeTab === 'drafts') {
      if (count > 0) {
        badge.textContent = count;
        badge.classList.add('visible');
      } else {
        badge.textContent = '0';
        badge.classList.remove('visible');
      }
    }
  }

  // ── Rendering ──

  renderDraftList() {
    // Skip re-render if user is actively editing — don't clobber their work
    if (this.draftList.querySelector('.fu-inline-edit-area')) return;

    // Split into three buckets
    const scheduled = this.drafts.filter(d => d.status === 'scheduled');
    const regularDrafts = this.drafts.filter(d => d.followup_section === 'drafts' && d.status !== 'scheduled');
    const followups = this.drafts.filter(d => d.followup_section !== 'drafts' && d.status !== 'scheduled');

    this.draftList.innerHTML = '';

    // 1. Drafts section (top, collapsed, always shown)
    this.draftList.appendChild(
      this._buildCollapsibleSection('drafts', 'Drafts', regularDrafts, this._draftsCollapsed !== false, (v) => { this._draftsCollapsed = v; })
    );

    // 2. Pending follow-ups (open, ungrouped)
    if (followups.length > 0) {
      followups.forEach(draft => {
        if (!draft.error) this.draftList.appendChild(this.buildDraftCard(draft));
      });
    } else if (regularDrafts.length > 0 && scheduled.length === 0) {
      const note = document.createElement('div');
      note.className = 'sidebar-empty';
      note.innerHTML = '<span class="empty-icon">&#10003;</span>No pending follow-ups';
      this.draftList.appendChild(note);
    }

    // 3. Scheduled section (bottom, collapsed, always shown)
    this.draftList.appendChild(
      this._buildCollapsibleSection('scheduled', 'Scheduled', scheduled, this._scheduledCollapsed !== false, (v) => { this._scheduledCollapsed = v; }, true)
    );
  }

  _buildCollapsibleSection(key, title, items, isCollapsed, onToggle, isScheduled = false) {
    const section = document.createElement('div');
    section.className = `fu-section fu-section-${key}`;

    const clockSvg = isScheduled
      ? '<svg class="fu-section-icon" width="13" height="13" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M8 4v4.5l3 1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg> '
      : '';

    section.innerHTML = `
      <button class="fu-section-header ${isCollapsed ? 'fu-section-collapsed' : ''}" aria-expanded="${!isCollapsed}">
        <span class="fu-section-chevron">${isCollapsed ? '▸' : '▾'}</span>
        <span class="fu-section-title">${clockSvg}${title}</span>
        <span class="fu-section-badge">${items.length}</span>
      </button>
      <div class="fu-section-body" style="${isCollapsed ? 'display:none' : ''}"></div>
    `;

    const header = section.querySelector('.fu-section-header');
    const body = section.querySelector('.fu-section-body');
    const chevron = section.querySelector('.fu-section-chevron');

    header.addEventListener('click', () => {
      const hidden = body.style.display === 'none';
      body.style.display = hidden ? '' : 'none';
      chevron.textContent = hidden ? '▾' : '▸';
      header.classList.toggle('fu-section-collapsed', !hidden);
      header.setAttribute('aria-expanded', hidden);
      onToggle(!hidden);
    });

    if (items.length === 0) {
      const emptyNote = document.createElement('div');
      emptyNote.className = 'fu-section-empty';
      emptyNote.textContent = `No ${title.toLowerCase()}`;
      body.appendChild(emptyNote);
    } else {
      items.forEach(item => {
        if (!item.error) {
          const card = isScheduled ? this.buildScheduledCard(item) : this.buildDraftCard(item);
          body.appendChild(card);
        }
      });
    }

    return section;
  }

  buildScheduledCard(item) {
    const card = document.createElement('div');
    card.className = 'draft-card sched-card';
    card.dataset.draftId = item.id;
    card.dataset.source = item.source || 'queue';

    // Format scheduled time
    const schedDate = new Date(item.scheduled_at);
    const timeStr = schedDate.toLocaleString('en-US', {
      weekday: 'short', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit', hour12: true,
    });

    const fuType = item.followup_icon || item.followup_type || 'draft';
    const badge = DraftsSidebar.TYPE_BADGES[fuType] || DraftsSidebar.TYPE_BADGES.draft;
    const badgeHtml = `<span class="fu-type-badge ${badge.cls}"><span class="fu-badge-icon">${badge.icon}</span><span class="fu-badge-label">${badge.label}</span></span>`;

    const subject = this.escapeHtml(item.subject || item.task_description || '(no subject)');
    const recipient = this.escapeHtml(item.to || item.from_person || '');

    card.innerHTML = `
      <div class="sched-card-time">${timeStr}</div>
      <div class="draft-card-header">
        ${badgeHtml}
        <div class="draft-card-actions">
          <button class="draft-btn draft-btn-discard" title="Cancel schedule">&#10005;</button>
        </div>
      </div>
      <div class="draft-card-subject">${subject}</div>
      ${recipient ? `<div class="draft-card-to">→ ${recipient}</div>` : ''}
    `;

    card.querySelector('.draft-btn-discard')?.addEventListener('click', () => {
      this.cancelSchedule(item.id, item.gmail_draft_id, card);
    });

    return card;
  }

  async cancelSchedule(itemId, gmailDraftId, card) {
    let liveCard = this.draftList.querySelector(`.draft-card[data-draft-id="${itemId}"]`) || card;
    const btn = liveCard?.querySelector('.draft-btn-discard');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '…';
    }

    try {
      const resp = await fetch(`/api/followups/${itemId}/unschedule`, { method: 'POST' });
      if (!resp.ok && resp.status !== 404) throw new Error(`HTTP ${resp.status}`);

      // Reload to move item from Scheduled back to pending
      await this.loadDrafts();
    } catch (e) {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '&#10005;';
      }
      alert(`Cancel failed: ${e.message}`);
    }
  }

  // Type badge config
  static TYPE_BADGES = {
    slack:    { icon: '<img src="https://a.slack-edge.com/80588/marketing/img/meta/favicon-32.png" class="fu-badge-favicon">', label: 'Slack',   cls: 'fu-badge-slack' },
    docs:     { icon: '<img src="https://ssl.gstatic.com/docs/documents/images/kix-favicon7.ico" class="fu-badge-favicon">', label: 'Comment', cls: 'fu-badge-docs' },
    meeting:  { icon: '<img src="https://www.granola.ai/favicon.ico" class="fu-badge-favicon">', label: 'Meeting', cls: 'fu-badge-meeting' },
    email:    { icon: '<img src="https://ssl.gstatic.com/ui/v1/icons/mail/rfr/gmail.ico" class="fu-badge-favicon">', label: 'Email',   cls: 'fu-badge-email' },
    draft:    { icon: '<img src="https://ssl.gstatic.com/ui/v1/icons/mail/rfr/gmail.ico" class="fu-badge-favicon">', label: 'Draft',   cls: 'fu-badge-draft' },
  };

  buildDraftCard(draft) {
    const card = document.createElement('div');
    card.className = 'draft-card';
    card.dataset.draftId = draft.id;
    card.dataset.source = draft.source || 'gmail';

    const fuType = draft.followup_icon || draft.followup_type || 'draft';
    const badge = DraftsSidebar.TYPE_BADGES[fuType] || DraftsSidebar.TYPE_BADGES.draft;
    const isDraft = fuType === 'draft';
    const badgeHtml = `<span class="fu-type-badge ${badge.cls}"><span class="fu-badge-icon">${badge.icon}</span><span class="fu-badge-label${isDraft ? ' fu-badge-italic' : ''}">${badge.label}</span></span>`;

    const isQueue = draft.source === 'queue';
    let contextLine = '';
    if (isQueue) {
      const loc = draft.location || draft.source_context || '';
      contextLine = `→ ${this.escapeHtml(draft.from_person || draft.to || '')}${loc ? ' in ' + this.escapeHtml(loc) : ''}`;
    } else {
      contextLine = `To: ${this.escapeHtml(draft.to || '(no recipient)')}`;
    }

    let sourcePreview = '';
    if (isQueue && draft.source_text) {
      const cleaned = draft.source_text.replace(/<@[A-Z0-9]+>/g, '').trim();
      sourcePreview = `<div class="fu-source-preview">${this.linkifyUrls(cleaned.slice(0, 300))}${cleaned.length > 300 ? '…' : ''}</div>`;
    }

    let draftPreview = '';
    if (isQueue && draft.draft_message) {
      draftPreview = `<div class="fu-draft-preview">${this.escapeHtml(draft.draft_message)}</div>`;
    }

    const timeLabel = draft.internalDate
      ? this.formatTime(new Date(parseInt(draft.internalDate)))
      : (draft.created_at ? this.formatTime(new Date(draft.created_at))
        : (draft.date ? this.formatTime(new Date(draft.date)) : ''));

    const names = draft.labelNames || [];
    const hasProposed = names.includes('Proposed');
    const extraLabels = hasProposed ? '<span class="draft-label draft-label-proposed">Proposed</span>' : '';

    const clockSvg = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M8 4v4.5l3 1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    const isDocsComment = draft.followup_type === 'docs_comment';
    const resolveBtn = isDocsComment
      ? `<button class="draft-btn draft-btn-resolve" title="Resolve comment">&#10003;</button>`
      : '';

    card.innerHTML = `
      <div class="draft-card-header">
        ${badgeHtml}
        <span class="draft-time">${this.escapeHtml(timeLabel)}</span>
        <div class="draft-card-actions">
          ${resolveBtn}
          <button class="draft-btn draft-btn-edit" title="Edit">&#9998;</button>
          <button class="draft-btn draft-btn-schedule" title="Schedule">${clockSvg}</button>
          <button class="draft-btn draft-btn-send" title="Send reply">&#10148;</button>
          <button class="draft-btn draft-btn-discard" title="Dismiss">&#10005;</button>
        </div>
      </div>
      <div class="draft-card-subject">${this.escapeHtml(draft.subject || draft.task_description || '(no subject)')}</div>
      <div class="draft-card-to">${contextLine}</div>
      ${sourcePreview}
      ${draftPreview}
      ${extraLabels ? `<div class="draft-card-meta">${extraLabels}</div>` : ''}
    `;

    card.querySelector('.draft-btn-edit')?.addEventListener('click', () => {
      if (isQueue && fuType === 'email') {
        this.openQueueEmailModal(draft);
      } else if (isQueue) {
        this.toggleInlineEdit(card, draft);
      } else {
        this.openEditModal(draft.id);
      }
    });
    card.querySelector('.draft-btn-schedule')?.addEventListener('click', () => {
      this.openScheduleModal(draft.id, draft.source || 'gmail', draft.subject || draft.task_description || '');
    });
    card.querySelector('.draft-btn-send').addEventListener('click', () => {
      if (isQueue) {
        const editor = card.querySelector('.fu-inline-editor');
        const message = editor ? editor.value : draft.draft_message;
        this.sendFollowup(draft.id, message, draft.from_person);
      } else {
        this.sendDraft(draft.id, draft.to);
      }
    });
    card.querySelector('.draft-btn-discard').addEventListener('click', () => this.discardDraft(draft.id, card));
    card.querySelector('.draft-btn-resolve')?.addEventListener('click', () => this.resolveComment(draft.id, card));

    return card;
  }

  async resolveComment(followupId, card) {
    const btn = card?.querySelector('.draft-btn-resolve');
    if (btn) { btn.disabled = true; btn.textContent = '\u2026'; }
    try {
      const resp = await fetch(`/api/followups/${followupId}/resolve`, { method: 'POST' });
      if (!resp.ok) {
        const data = await resp.json();
        throw new Error(data.error || `HTTP ${resp.status}`);
      }
      this.drafts = this.drafts.filter(d => d.id !== followupId);
      this.updateBadge(this.drafts.length);
      this.renderDraftList();
    } catch (e) {
      alert(`Resolve failed: ${e.message}`);
      if (btn) { btn.disabled = false; btn.textContent = '\u2713'; }
    }
  }

  formatTime(date) {
    try {
      const now = new Date();
      const diffMs = now - date;
      const diffHours = diffMs / (1000 * 60 * 60);

      if (diffHours < 1) return `${Math.max(1, Math.floor(diffMs / 60000))}m ago`;
      if (diffHours < 24) return `${Math.floor(diffHours)}h ago`;
      if (diffHours < 48) return 'yesterday';
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  }

  // ── Schedule ──

  bindScheduleEvents() {
    // Schedule panel controls
    document.getElementById('schedule-cancel-x')?.addEventListener('click', () => this.closeScheduleModal());
    document.getElementById('schedule-cancel-btn')?.addEventListener('click', () => this.closeScheduleModal());

    // Panel quick buttons
    document.querySelectorAll('#schedule-panel .sched-quick-btn').forEach(btn => {
      btn.addEventListener('click', () => this.onQuickBtnClick(btn, 'modal'));
    });

    // Panel custom confirm
    document.getElementById('schedule-confirm-btn')?.addEventListener('click', () => this.scheduleCustom('modal'));

    // Panel picker → enable confirm
    const dateInput = document.getElementById('schedule-date');
    const timeInput = document.getElementById('schedule-time');
    const enableConfirm = () => {
      document.getElementById('schedule-confirm-btn').disabled = !(dateInput?.value && timeInput?.value);
    };
    dateInput?.addEventListener('change', enableConfirm);
    timeInput?.addEventListener('change', enableConfirm);

    // Click outside panel to dismiss
    document.addEventListener('click', (e) => {
      const panel = document.getElementById('schedule-panel');
      if (panel?.classList.contains('visible') && !panel.contains(e.target) && !e.target.closest('.draft-btn-schedule')) {
        this.closeScheduleModal();
      }
    });

    // Edit modal schedule toggle
    document.getElementById('draft-edit-schedule-btn')?.addEventListener('click', () => this.toggleEditSchedule());

    // Edit modal inline quick buttons
    document.querySelectorAll('#draft-edit-schedule .sched-quick-btn').forEach(btn => {
      btn.addEventListener('click', () => this.onQuickBtnClick(btn, 'edit'));
    });

    // Edit modal inline confirm
    document.getElementById('draft-sched-confirm')?.addEventListener('click', () => this.scheduleCustom('edit'));

    // Edit modal inline picker → enable confirm
    const editDate = document.getElementById('draft-sched-date');
    const editTime = document.getElementById('draft-sched-time');
    const enableEditConfirm = () => {
      const btn = document.getElementById('draft-sched-confirm');
      if (btn) btn.disabled = !(editDate?.value && editTime?.value);
    };
    editDate?.addEventListener('change', enableEditConfirm);
    editTime?.addEventListener('change', enableEditConfirm);
  }

  openScheduleModal(id, source, description) {
    this.pendingScheduleId = id;
    this.pendingScheduleSource = source;

    const panel = document.getElementById('schedule-panel');
    document.getElementById('schedule-preview').textContent = description || id;

    this.updateQuickDayLabels(panel);
    document.getElementById('schedule-date').value = '';
    document.getElementById('schedule-time').value = '';
    document.getElementById('schedule-confirm-btn').disabled = true;

    // Position the panel as a fixed overlay below the triggering card
    const card = this.draftList.querySelector(`.draft-card[data-draft-id="${id}"]`);
    if (card) {
      const sidebar = card.closest('aside');
      const cardRect = card.getBoundingClientRect();
      const sidebarRect = sidebar ? sidebar.getBoundingClientRect() : cardRect;

      panel.style.position = 'fixed';
      panel.style.left = `${sidebarRect.left + 12}px`;
      panel.style.width = `${sidebarRect.width - 24}px`;

      // Try below the card; if no room, put above
      const spaceBelow = window.innerHeight - cardRect.bottom - 8;
      const panelHeight = 220; // approximate
      if (spaceBelow >= panelHeight) {
        panel.style.top = `${cardRect.bottom + 4}px`;
        panel.style.bottom = 'auto';
      } else {
        panel.style.bottom = `${window.innerHeight - cardRect.top + 4}px`;
        panel.style.top = 'auto';
      }
    }

    panel.classList.add('visible');
  }

  closeScheduleModal() {
    const panel = document.getElementById('schedule-panel');
    if (panel) {
      panel.classList.remove('visible');
      panel.style.position = '';
      panel.style.left = '';
      panel.style.width = '';
      panel.style.top = '';
      panel.style.bottom = '';
    }
    this.pendingScheduleId = null;
    this.pendingScheduleSource = null;
  }

  toggleEditSchedule() {
    const section = document.getElementById('draft-edit-schedule');
    const isVisible = section.style.display !== 'none';
    section.style.display = isVisible ? 'none' : '';

    if (!isVisible) {
      this.updateQuickDayLabels(section);
      document.getElementById('draft-sched-date').value = '';
      document.getElementById('draft-sched-time').value = '';
      const btn = document.getElementById('draft-sched-confirm');
      if (btn) btn.disabled = true;
      section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  updateQuickDayLabels(container) {
    container.querySelectorAll('.sched-quick-btn').forEach(btn => {
      const h = parseInt(btn.dataset.hour);
      const m = parseInt(btn.dataset.min);
      btn.querySelector('.sqb-day').textContent = this.getQuickDayLabel(h, m);
    });
  }

  getQuickDayLabel(hour, minute) {
    const now = new Date();
    const cutoff = new Date(now);
    cutoff.setHours(hour, minute + 12, 0, 0);
    return now >= cutoff ? 'Tomorrow' : 'Today';
  }

  getNextQuickTime(hour, minute) {
    const jitter = Math.floor(Math.random() * 25) - 12; // ±12 minutes
    const d = new Date();
    let h = hour;
    let m = minute + jitter;
    if (m < 0) { h--; m += 60; }
    if (m >= 60) { h++; m -= 60; }
    d.setHours(h, m, Math.floor(Math.random() * 60), 0);
    // If this time has already passed, push to tomorrow
    if (d <= new Date()) {
      d.setDate(d.getDate() + 1);
    }
    return d;
  }

  async onQuickBtnClick(btn, context) {
    const h = parseInt(btn.dataset.hour);
    const m = parseInt(btn.dataset.min);
    const sendAt = this.getNextQuickTime(h, m);

    // Show scheduling feedback
    const origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="sqb-time">Scheduling\u2026</span>';

    if (context === 'modal') {
      await this.scheduleItem(this.pendingScheduleId, this.pendingScheduleSource, sendAt);
      btn.innerHTML = '<span class="sqb-time">\u2713</span>';
      setTimeout(() => this.closeScheduleModal(), 400);
    } else {
      // Edit modal context
      const overlay = document.getElementById('draft-edit-overlay');
      const draftId = overlay.dataset.draftId;
      const draft = this.drafts.find(d => d.id === draftId);
      const source = draft?.source || 'gmail';

      // Save edits first for gmail drafts
      if (source !== 'queue') {
        await this.saveBeforeSchedule(draftId);
      }
      await this.scheduleItem(draftId, source, sendAt);
      btn.innerHTML = '<span class="sqb-time">\u2713</span>';
      setTimeout(() => this.closeEditModal(), 400);
    }
  }

  async scheduleCustom(context) {
    let dateStr, timeStr, id, source, confirmBtn;

    if (context === 'modal') {
      dateStr = document.getElementById('schedule-date').value;
      timeStr = document.getElementById('schedule-time').value;
      confirmBtn = document.getElementById('schedule-confirm-btn');
      id = this.pendingScheduleId;
      source = this.pendingScheduleSource;
    } else {
      dateStr = document.getElementById('draft-sched-date').value;
      timeStr = document.getElementById('draft-sched-time').value;
      confirmBtn = document.getElementById('draft-sched-confirm');
      const overlay = document.getElementById('draft-edit-overlay');
      id = overlay.dataset.draftId;
      const draft = this.drafts.find(d => d.id === id);
      source = draft?.source || 'gmail';

      if (source !== 'queue') {
        await this.saveBeforeSchedule(id);
      }
    }

    if (!dateStr || !timeStr) return;

    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.textContent = 'Scheduling\u2026';
    }

    const sendAt = new Date(`${dateStr}T${timeStr}`);
    await this.scheduleItem(id, source, sendAt);

    if (confirmBtn) confirmBtn.textContent = '\u2713';
    if (context === 'modal') {
      setTimeout(() => this.closeScheduleModal(), 400);
    } else {
      setTimeout(() => this.closeEditModal(), 400);
    }
  }

  async saveBeforeSchedule(draftId) {
    const resp = await fetch(`/api/drafts/${draftId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(this.collectFormData()),
    });
    if (!resp.ok) throw new Error('Failed to save draft');
  }

  async scheduleItem(id, source, sendAt) {
    const endpoint = source === 'queue'
      ? `/api/followups/${id}/schedule`
      : `/api/drafts/${id}/schedule`;

    // Include metadata so backend can create a tracking entry
    const draft = this.drafts.find(d => d.id === id);
    const payload = { send_at: sendAt.toISOString() };
    if (source !== 'queue' && draft) {
      payload.subject = draft.subject || '';
      payload.to = draft.to || '';
      payload.followup_type = draft.followup_type || 'draft';
      payload.followup_icon = draft.followup_icon || 'draft';
    }

    try {
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const data = await resp.json();
        throw new Error(data.error || `HTTP ${resp.status}`);
      }

      // Reload to move item into Scheduled section
      await this.loadDrafts();
    } catch (e) {
      alert(`Schedule failed: ${e.message}`);
    }
  }

  // ── Rich Text Toolbar ──

  initToolbar() {
    if (this._toolbarReady) return;
    this._toolbarReady = true;

    document.querySelectorAll('.draft-toolbar .tb-btn').forEach(btn => {
      btn.addEventListener('mousedown', e => e.preventDefault());
      btn.addEventListener('click', () => {
        const cmd = btn.dataset.cmd;
        const body = document.getElementById('draft-edit-body');
        body.focus();

        if (cmd === 'createLink') {
          const url = prompt('Enter URL:');
          if (url) document.execCommand('createLink', false, url);
        } else {
          document.execCommand(cmd, false, null);
        }
        this.updateToolbarState();
      });
    });

    document.getElementById('draft-edit-body')?.addEventListener('keyup', () => this.updateToolbarState());
    document.getElementById('draft-edit-body')?.addEventListener('mouseup', () => this.updateToolbarState());
  }

  updateToolbarState() {
    document.querySelectorAll('.draft-toolbar .tb-btn[data-cmd]').forEach(btn => {
      const cmd = btn.dataset.cmd;
      if (['bold', 'italic', 'underline', 'insertUnorderedList', 'insertOrderedList'].includes(cmd)) {
        btn.classList.toggle('active', document.queryCommandState(cmd));
      }
    });
  }

  // ── Edit Modal ──

  getBodyHtml() {
    return document.getElementById('draft-edit-body').innerHTML;
  }

  setBodyHtml(html) {
    document.getElementById('draft-edit-body').innerHTML = html || '';
  }

  async openEditModal(draftId) {
    this.initToolbar();

    const overlay = document.getElementById('draft-edit-overlay');
    const toInput = document.getElementById('draft-edit-to');
    const ccInput = document.getElementById('draft-edit-cc');
    const subjectInput = document.getElementById('draft-edit-subject');
    const errorEl = document.getElementById('draft-edit-error');

    toInput.value = '';
    ccInput.value = '';
    subjectInput.value = '';
    this.setBodyHtml('');
    errorEl.textContent = '';
    errorEl.style.display = 'none';
    overlay.dataset.draftId = draftId;

    // Reset schedule section
    document.getElementById('draft-edit-schedule').style.display = 'none';

    overlay.classList.add('visible');

    try {
      const resp = await fetch(`/api/drafts/${draftId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      toInput.value = data.to || '';
      ccInput.value = data.cc || '';
      subjectInput.value = data.subject || '';
      this.setBodyHtml(data.body || '');
    } catch (e) {
      errorEl.textContent = `Failed to load draft: ${e.message}`;
      errorEl.style.display = 'block';
    }
  }

  collectFormData() {
    return {
      to: document.getElementById('draft-edit-to').value,
      cc: document.getElementById('draft-edit-cc').value,
      subject: document.getElementById('draft-edit-subject').value,
      body: this.getBodyHtml(),
    };
  }

  async saveDraft() {
    const overlay = document.getElementById('draft-edit-overlay');
    const draftId = overlay.dataset.draftId;
    const isQueueEmail = overlay.dataset.queueEmail === 'true';
    const errorEl = document.getElementById('draft-edit-error');
    const saveBtn = document.getElementById('draft-edit-save-btn');

    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving\u2026';
    errorEl.style.display = 'none';

    try {
      if (isQueueEmail) {
        const formData = this.collectFormData();
        const resp = await fetch(`/api/followups/${draftId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            draft_message: formData.body,
            subject: formData.subject,
            to: formData.to,
          }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      } else {
        const resp = await fetch(`/api/drafts/${draftId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.collectFormData()),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      }

      this.closeEditModal();
      await this.loadDrafts();
    } catch (e) {
      errorEl.textContent = `Save failed: ${e.message}`;
      errorEl.style.display = 'block';
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Draft';
    }
  }

  async sendFromModal() {
    const overlay = document.getElementById('draft-edit-overlay');
    const draftId = overlay.dataset.draftId;
    const isQueueEmail = overlay.dataset.queueEmail === 'true';
    const to = document.getElementById('draft-edit-to').value;

    const errorEl = document.getElementById('draft-edit-error');
    const sendBtn = document.getElementById('draft-edit-send-btn');

    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending\u2026';
    errorEl.style.display = 'none';

    try {
      if (isQueueEmail) {
        // Save edits then send via follow-up endpoint
        const formData = this.collectFormData();
        await fetch(`/api/followups/${draftId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            draft_message: formData.body,
            subject: formData.subject,
            to: formData.to,
          }),
        });

        const resp = await fetch(`/api/followups/${draftId}/send`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: formData.body }),
        });
        if (!resp.ok) {
          const data = await resp.json();
          throw new Error(data.error || `HTTP ${resp.status}`);
        }
      } else {
        const saveResp = await fetch(`/api/drafts/${draftId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.collectFormData()),
        });
        if (!saveResp.ok) throw new Error(`Save failed: HTTP ${saveResp.status}`);

        const resp = await fetch(`/api/drafts/${draftId}/send`, { method: 'POST' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      }

      this.closeEditModal();
      this.drafts = this.drafts.filter(d => d.id !== draftId);
      this.updateBadge(this.drafts.length);
      this.renderDraftList();
    } catch (e) {
      errorEl.textContent = `Send failed: ${e.message}`;
      errorEl.style.display = 'block';
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = 'Send';
    }
  }

  openQueueEmailModal(draft) {
    this.initToolbar();

    const overlay = document.getElementById('draft-edit-overlay');
    const toInput = document.getElementById('draft-edit-to');
    const ccInput = document.getElementById('draft-edit-cc');
    const subjectInput = document.getElementById('draft-edit-subject');
    const errorEl = document.getElementById('draft-edit-error');

    toInput.value = draft.to || draft.from_person || '';
    ccInput.value = '';
    subjectInput.value = draft.subject || draft.task_description || '';
    this.setBodyHtml(draft.draft_message || '');
    errorEl.textContent = '';
    errorEl.style.display = 'none';

    // Tag this as a queue email edit so save/send use the right endpoints
    overlay.dataset.draftId = draft.id;
    overlay.dataset.queueEmail = 'true';

    // Reset schedule section
    const schedSection = document.getElementById('draft-edit-schedule');
    if (schedSection) schedSection.style.display = 'none';

    overlay.classList.add('visible');
  }

  closeEditModal() {
    const overlay = document.getElementById('draft-edit-overlay');
    if (overlay) {
      overlay.classList.remove('visible');
      delete overlay.dataset.queueEmail;
    }
  }

  // ── Card Actions ──

  toggleInlineEdit(card, draft) {
    const existing = card.querySelector('.fu-inline-edit-area');
    if (existing) {
      // Save on close
      const textarea = existing.querySelector('.fu-inline-editor');
      if (textarea) {
        const newMsg = textarea.value.trim();
        if (newMsg && newMsg !== draft.draft_message) {
          draft.draft_message = newMsg;
          this.saveFollowupMessage(draft.id, newMsg);
          // Update the preview text
          const preview = card.querySelector('.fu-draft-preview');
          if (preview) preview.textContent = newMsg;
        }
      }
      existing.remove();
      const preview = card.querySelector('.fu-draft-preview');
      if (preview) preview.style.display = '';
      return;
    }

    const preview = card.querySelector('.fu-draft-preview');
    if (preview) preview.style.display = 'none';

    const editArea = document.createElement('div');
    editArea.className = 'fu-inline-edit-area';
    editArea.innerHTML = `
      <textarea class="fu-inline-editor" rows="3">${this.escapeHtml(draft.draft_message || '')}</textarea>
    `;

    const insertAfter = card.querySelector('.fu-source-preview') || card.querySelector('.draft-card-to');
    if (insertAfter) {
      insertAfter.after(editArea);
    } else {
      card.appendChild(editArea);
    }

    const textarea = editArea.querySelector('.fu-inline-editor');
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    // Auto-save on blur
    textarea.addEventListener('blur', () => {
      const newMsg = textarea.value.trim();
      if (newMsg && newMsg !== draft.draft_message) {
        draft.draft_message = newMsg;
        this.saveFollowupMessage(draft.id, newMsg);
        const preview = card.querySelector('.fu-draft-preview');
        if (preview) preview.textContent = newMsg;
      }
    });
  }

  async saveFollowupMessage(followupId, message) {
    try {
      await fetch(`/api/followups/${followupId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft_message: message }),
      });
    } catch { /* silent */ }
  }

  async sendFollowup(followupId, message, to) {
    let card = this.draftList.querySelector(`.draft-card[data-draft-id="${followupId}"]`);
    const sendBtn = card?.querySelector('.draft-btn-send');
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.innerHTML = '…';
    }

    try {
      const resp = await fetch(`/api/followups/${followupId}/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
      if (!resp.ok) {
        const data = await resp.json();
        throw new Error(data.error || `HTTP ${resp.status}`);
      }

      // Re-resolve after await in case poll replaced the card
      card = this.draftList.querySelector(`.draft-card[data-draft-id="${followupId}"]`) || card;
      if (card) this.removeCard(card);
      this.drafts = this.drafts.filter(d => d.id !== followupId);
      this.updateBadge(this.drafts.length);
    } catch (e) {
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.innerHTML = '&#10148;';
      }
      alert(`Send failed: ${e.message}`);
    }
  }

  async sendDraft(draftId, to) {
    const card = this.draftList.querySelector(`.draft-card[data-draft-id="${draftId}"]`);
    const sendBtn = card?.querySelector('.draft-btn-send');
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.innerHTML = '…';
    }

    try {
      const resp = await fetch(`/api/drafts/${draftId}/send`, { method: 'POST' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const card = this.draftList.querySelector(`.draft-card[data-draft-id="${draftId}"]`);
      if (card) this.removeCard(card);
      this.drafts = this.drafts.filter(d => d.id !== draftId);
      this.updateBadge(this.drafts.length);
    } catch (e) {
      alert(`Send failed: ${e.message}`);
    }
  }

  async discardDraft(draftId, card) {
    // Re-resolve card from DOM in case poll replaced it
    let liveCard = this.draftList.querySelector(`.draft-card[data-draft-id="${draftId}"]`) || card;
    const discardBtn = liveCard?.querySelector('.draft-btn-discard');
    if (discardBtn) {
      discardBtn.disabled = true;
      discardBtn.innerHTML = '…';
    }

    try {
      const resp = await fetch(`/api/drafts/${draftId}`, { method: 'DELETE' });
      if (!resp.ok && resp.status !== 404) throw new Error(`HTTP ${resp.status}`);

      // Re-resolve again after await
      liveCard = this.draftList.querySelector(`.draft-card[data-draft-id="${draftId}"]`) || liveCard;
      if (liveCard) this.removeCard(liveCard);
      this.drafts = this.drafts.filter(d => d.id !== draftId);
      this.updateBadge(this.drafts.length);
    } catch (e) {
      if (discardBtn) {
        discardBtn.disabled = false;
        discardBtn.innerHTML = '&#10005;';
      }
      alert(`Discard failed: ${e.message}`);
    }
  }

  removeCard(card) {
    card.classList.add('removing');
    card.addEventListener('transitionend', () => card.remove(), { once: true });
    setTimeout(() => { if (card.parentNode) card.remove(); }, 500);
  }

  // ── Utilities ──

  escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  linkifyUrls(str) {
    if (!str) return '';
    const escaped = this.escapeHtml(str);
    return escaped.replace(
      /https?:\/\/[^\s<)]+/g,
      url => `<a href="${url}" target="_blank" rel="noopener">${url}</a>`
    );
  }
}
