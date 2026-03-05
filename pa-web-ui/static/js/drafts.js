// Gmail Drafts Sidebar — view, edit, send, and discard agent-generated drafts

class DraftsSidebar {
  constructor(taskSidebar) {
    this.taskSidebar = taskSidebar;
    this.drafts = [];
    this.pollInterval = null;
    this.draftList = document.getElementById('draft-list');
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
    if (this.drafts.length === 0) {
      this.draftList.innerHTML = '<div class="sidebar-empty"><span class="empty-icon">&#9993;</span>No drafts</div>';
      return;
    }

    this.draftList.innerHTML = '';
    this.drafts.forEach(draft => {
      if (!draft.error) {
        this.draftList.appendChild(this.buildDraftCard(draft));
      }
    });
  }

  buildDraftCard(draft) {
    const card = document.createElement('div');
    card.className = 'draft-card';
    card.dataset.draftId = draft.id;

    // Use resolved label names from gws-bridge
    const names = draft.labelNames || [];
    const hasFollowup = names.includes('Followup');
    const hasProposed = names.includes('Proposed');
    const labelTags = (hasFollowup ? '<span class="draft-label">Followup</span>' : '')
      + (hasProposed ? '<span class="draft-label draft-label-proposed">Proposed</span>' : '');

    const timeLabel = draft.internalDate
      ? this.formatTime(new Date(parseInt(draft.internalDate)))
      : (draft.date ? this.formatTime(new Date(draft.date)) : '');

    card.innerHTML = `
      <div class="draft-card-body">
        <div class="draft-card-subject">${this.escapeHtml(draft.subject || '(no subject)')}</div>
        <div class="draft-card-to">To: ${this.escapeHtml(draft.to || '(no recipient)')}</div>
        <div class="draft-card-meta">
          ${labelTags}
          <span class="draft-time">${this.escapeHtml(timeLabel)}</span>
        </div>
      </div>
      <div class="draft-card-actions">
        <button class="draft-btn draft-btn-edit" title="Edit">&#9998;</button>
        <button class="draft-btn draft-btn-send" title="Send">&#10148;</button>
        <button class="draft-btn draft-btn-discard" title="Discard">&#10005;</button>
      </div>
    `;

    card.querySelector('.draft-btn-edit').addEventListener('click', () => this.openEditModal(draft.id));
    card.querySelector('.draft-btn-send').addEventListener('click', () => this.sendDraft(draft.id, draft.to));
    card.querySelector('.draft-btn-discard').addEventListener('click', () => this.discardDraft(draft.id, card));

    return card;
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

  // ── Edit Modal ──

  async openEditModal(draftId) {
    const overlay = document.getElementById('draft-edit-overlay');
    const toInput = document.getElementById('draft-edit-to');
    const ccInput = document.getElementById('draft-edit-cc');
    const subjectInput = document.getElementById('draft-edit-subject');
    const bodyInput = document.getElementById('draft-edit-body');
    const errorEl = document.getElementById('draft-edit-error');

    // Reset
    toInput.value = '';
    ccInput.value = '';
    subjectInput.value = '';
    bodyInput.value = '';
    errorEl.textContent = '';
    errorEl.style.display = 'none';
    overlay.dataset.draftId = draftId;

    overlay.classList.add('visible');

    // Load full draft
    try {
      const resp = await fetch(`/api/drafts/${draftId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      toInput.value = data.to || '';
      ccInput.value = data.cc || '';
      subjectInput.value = data.subject || '';
      bodyInput.value = data.body || '';
    } catch (e) {
      errorEl.textContent = `Failed to load draft: ${e.message}`;
      errorEl.style.display = 'block';
    }
  }

  async saveDraft() {
    const overlay = document.getElementById('draft-edit-overlay');
    const draftId = overlay.dataset.draftId;
    const errorEl = document.getElementById('draft-edit-error');
    const saveBtn = document.getElementById('draft-edit-save-btn');

    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving\u2026';
    errorEl.style.display = 'none';

    try {
      const resp = await fetch(`/api/drafts/${draftId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to: document.getElementById('draft-edit-to').value,
          cc: document.getElementById('draft-edit-cc').value,
          subject: document.getElementById('draft-edit-subject').value,
          body: document.getElementById('draft-edit-body').value,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

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
    const to = document.getElementById('draft-edit-to').value;

    // Save first, then send
    const errorEl = document.getElementById('draft-edit-error');
    const sendBtn = document.getElementById('draft-edit-send-btn');

    if (!confirm(`Send this email to ${to}?`)) return;

    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending\u2026';
    errorEl.style.display = 'none';

    try {
      // Save current edits first
      const saveResp = await fetch(`/api/drafts/${draftId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to: document.getElementById('draft-edit-to').value,
          cc: document.getElementById('draft-edit-cc').value,
          subject: document.getElementById('draft-edit-subject').value,
          body: document.getElementById('draft-edit-body').value,
        }),
      });
      if (!saveResp.ok) throw new Error(`Save failed: HTTP ${saveResp.status}`);

      // Send
      const resp = await fetch(`/api/drafts/${draftId}/send`, { method: 'POST' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

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

  closeEditModal() {
    document.getElementById('draft-edit-overlay')?.classList.remove('visible');
  }

  // ── Card Actions ──

  async sendDraft(draftId, to) {
    if (!confirm(`Send this email to ${to || 'recipient'}?`)) return;

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
    if (!confirm('Permanently delete this draft?')) return;

    try {
      const resp = await fetch(`/api/drafts/${draftId}`, { method: 'DELETE' });
      if (!resp.ok && resp.status !== 404) throw new Error(`HTTP ${resp.status}`);

      this.removeCard(card);
      this.drafts = this.drafts.filter(d => d.id !== draftId);
      this.updateBadge(this.drafts.length);
    } catch (e) {
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
}
