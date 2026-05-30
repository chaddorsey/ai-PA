// Phase 2 — Conversation switcher rail (left-side panel).
// Loaded before chat.js; chat.js instantiates `window.conversationRail` and
// calls `window.chatUI.switchConversation(id)` on rail row-click.
//
// Responsibilities:
// - Fetch the conversation list from /api/conversations (Letta + meta JOIN)
// - Resolve the initial selection from localStorage['pa_last_conv_id']
// - Render one flat row per conversation; inline-edit rename; ⋯ dropdown
// - Create: new row in edit mode → POST on commit
// - Delete: optimistic hide + 10s undo toast → DELETE on expiry
// - Receive external label updates (from the SSE auto-rename event)

(function () {
  'use strict';

  const LAST_CONV_KEY = 'pa_last_conv_id';
  const UNDO_WINDOW_MS = 10000;

  function $(id) { return document.getElementById(id); }

  async function csrfHeaders(extra = {}) {
    // Defined in chat.js / sidebar.js as a module-scoped helper; prefer
    // sidebar.js's global if present.
    if (typeof paCsrfHeaders === 'function') {
      return await paCsrfHeaders(extra);
    }
    // Fallback: fetch the token if the other scripts haven't loaded yet.
    try {
      const resp = await fetch('/api/csrf-token', { credentials: 'same-origin' });
      const data = await resp.json();
      return { ...extra, 'X-CSRF-Token': data.csrf_token };
    } catch {
      return extra;
    }
  }

  function formatTimestamp(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return '';
    const now = new Date();
    const diffMs = now - d;
    const diffH = diffMs / (1000 * 60 * 60);
    if (diffH < 24 && now.getDate() === d.getDate()) {
      return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }
    if (diffH < 24 * 7) {
      return d.toLocaleDateString([], { weekday: 'short' });
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  class UndoToast {
    /**
     * Show an undo toast with a 10s countdown. On Undo click, calls
     * onUndo(). Otherwise, calls onCommit() when timer expires OR the
     * user dismisses the toast with the ✕ button.
     */
    constructor({ text, onUndo, onCommit }) {
      this.onUndo = onUndo;
      this.onCommit = onCommit;
      this.committed = false;

      const container = $('undo-toast-container');
      const toast = document.createElement('div');
      toast.className = 'undo-toast';

      const textEl = document.createElement('span');
      textEl.className = 'undo-toast-text';
      textEl.textContent = text;
      toast.appendChild(textEl);

      const undoBtn = document.createElement('button');
      undoBtn.className = 'undo-toast-btn';
      undoBtn.textContent = 'Undo';
      undoBtn.addEventListener('click', () => this._handleUndo());
      toast.appendChild(undoBtn);

      const dismissBtn = document.createElement('button');
      dismissBtn.className = 'undo-toast-dismiss';
      dismissBtn.innerHTML = '&times;';
      dismissBtn.title = 'Dismiss (commits the action)';
      dismissBtn.addEventListener('click', () => this._handleCommit());
      toast.appendChild(dismissBtn);

      const progress = document.createElement('div');
      progress.className = 'undo-toast-progress';
      toast.appendChild(progress);

      this.el = toast;
      container.appendChild(toast);
      this.timer = setTimeout(() => this._handleCommit(), UNDO_WINDOW_MS);
    }

    _handleUndo() {
      if (this.committed) return;
      this.committed = true;
      clearTimeout(this.timer);
      this.el.remove();
      try { this.onUndo(); } catch (e) { console.error('[undo-toast] onUndo failed', e); }
    }

    _handleCommit() {
      if (this.committed) return;
      this.committed = true;
      clearTimeout(this.timer);
      this.el.remove();
      try { this.onCommit(); } catch (e) { console.error('[undo-toast] onCommit failed', e); }
    }
  }

  class ConversationRail {
    constructor() {
      this.rail = $('conversation-rail');
      this.toggle = $('conversation-rail-toggle');
      this.list = $('conv-list');
      this.newBtn = $('conv-new-btn');
      this.closeBtn = $('conv-rail-close');
      this.taskSidebar = $('task-sidebar');
      this.taskSidebarToggle = $('sidebar-toggle');

      this.conversations = [];      // list from server
      this.selectedId = null;
      this.hiddenIds = new Set();   // optimistically hidden during delete undo window

      this._bindToggle();
      this._bindNewButton();
      this._bindGlobalClickToCloseDropdowns();
    }

    async init() {
      // Seed currentAgentId from the picker so the very first fetch
      // hits the right agent's workspace. Without this, the first
      // refresh defaults to MC on the server side, but localStorage
      // might point at a non-MC conv → mismatch and confusion.
      const picker = document.getElementById('agent-select');
      const pickerAgent = (picker && picker.value || '').trim();
      if (pickerAgent && !this.currentAgentId) {
        this.currentAgentId = pickerAgent;
        this._updateBadge(pickerAgent);
      }
      await this.refresh();
      const selected = this._pickInitialSelection();
      if (selected) {
        this.selectedId = selected;
        this.render();
        if (window.chatUI && typeof window.chatUI.switchConversation === 'function') {
          await window.chatUI.switchConversation(selected);
        }
      } else {
        this.render();
      }
    }

    async refresh() {
      // The sidebar is scoped to the currently-selected agent in the
      // header picker. When the picker changes, refresh() is re-called
      // and the rail re-fetches for that agent's workspace.
      const agentId = (this.currentAgentId || '').trim();
      const url = agentId
        ? `/api/conversations?agent_id=${encodeURIComponent(agentId)}`
        : '/api/conversations';
      try {
        const resp = await fetch(url, { credentials: 'same-origin' });
        if (!resp.ok) {
          if (resp.status === 503) {
            // Phase 2 flag is off; render empty rail silently.
            this.conversations = [];
            return;
          }
          throw new Error(`HTTP ${resp.status}`);
        }
        const data = await resp.json();
        this.conversations = data.conversations || [];
      } catch (err) {
        console.warn('[conv-rail] fetch failed', err);
        this.conversations = [];
      }
    }

    /**
     * Update the rail's agent filter. Re-fetches conversation list and
     * re-renders. Called by chat.js when the header agent picker
     * changes.
     */
    async setAgent(agentId) {
      const next = (agentId || '').trim();
      if (next === (this.currentAgentId || '')) return;
      this.currentAgentId = next;
      this._updateBadge(next);
      await this.refresh();
      this.render();
    }

    /** Update the sidebar's current-agent badge to reflect agent id. */
    _updateBadge(agentId) {
      const badge = document.getElementById('conv-rail-agent-badge');
      if (!badge) return;
      const labelEl = badge.querySelector('.badge-label');
      const map = {
        'agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef': ['Mission Control', 'mc'],
        'agent-dd15479e-6543-400e-8463-b2a48b13cd4a': ['Task Agent', 'tasks'],
        'agent-892a2d58-b9f6-4baf-84f3-c431fe46487d': ['Calendar Agent', 'calendar'],
        'agent-2ed14ef4-6289-453a-ae27-290b6ed196b8': ['Pulse Agent', 'pulse'],
        'agent-398b4f6c-6afa-493f-8063-897c6b171a0d': ['Documents Agent', 'documents'],
        'agent-b4928949-8012-4436-a3c7-a9e510785147': ['Email Agent', 'email'],
      };
      const [label, slug] = map[agentId] || ['Mission Control', 'mc'];
      if (labelEl) labelEl.textContent = label;
      badge.setAttribute('data-agent', slug);
    }

    _pickInitialSelection() {
      const saved = localStorage.getItem(LAST_CONV_KEY);
      // Only honor the saved conv if it actually belongs to the
      // currently-scoped agent's workspace. Otherwise we'd silently
      // jump the user into a different agent's conversation on page
      // load (the source of the "I think I'm on MC but I'm getting
      // calendar context" bug).
      const inCurrentScope = saved && this.conversations.some(
        (c) => c.id === saved,
      );
      if (inCurrentScope) return saved;
      // MRU fallback within the current agent's list.
      return this.conversations.length ? this.conversations[0].id : null;
    }

    render() {
      this.list.innerHTML = '';

      const visible = this.conversations.filter((c) => !this.hiddenIds.has(c.id));
      if (visible.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'conv-empty-state';
        empty.textContent = 'No conversations yet. Click + to start one.';
        this.list.appendChild(empty);
        return;
      }

      const parentLookup = new Set(visible.map((c) => c.id));
      for (const c of visible) {
        this.list.appendChild(this._renderRow(c, parentLookup));
      }
    }

    _renderRow(c, parentLookup) {
      const row = document.createElement('div');
      row.className = 'conv-row';
      row.dataset.convId = c.id;
      if (c.id === this.selectedId) row.classList.add('selected');
      if (c.parent_conversation_id && parentLookup.has(c.parent_conversation_id)) {
        row.classList.add('fork-child');
      }

      // Whole-row click → switch. Single click anywhere on the row works;
      // the label, timestamp, and empty-space all count. The ⋯ menu and
      // in-place rename stop propagation below so they don't trigger a
      // switch when the user is interacting with them.
      row.addEventListener('click', (ev) => {
        if (row.dataset.editing) return;
        // Interactive children stop propagation themselves; if this
        // handler fires, it's a row-level intent.
        this.switchTo(c.id);
      });

      const labelEl = document.createElement('span');
      labelEl.className = 'conv-row-label';
      labelEl.textContent = c.label || '(untitled)';
      labelEl.addEventListener('dblclick', (ev) => {
        ev.stopPropagation();
        this._enterRenameMode(row, labelEl, c.id);
      });
      row.appendChild(labelEl);

      const tsEl = document.createElement('span');
      tsEl.className = 'conv-row-ts';
      tsEl.textContent = formatTimestamp(c.last_message_at || c.created_at);
      row.appendChild(tsEl);

      const menuBtn = document.createElement('button');
      menuBtn.className = 'conv-row-menu';
      menuBtn.innerHTML = '⋯';
      menuBtn.title = 'More';
      menuBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        this._toggleMenu(row, c.id);
      });
      row.appendChild(menuBtn);

      return row;
    }

    _toggleMenu(row, convId) {
      // Close any open menus first.
      document.querySelectorAll('.conv-row-menu-dropdown').forEach((el) => el.remove());

      const dropdown = document.createElement('div');
      dropdown.className = 'conv-row-menu-dropdown';

      const renameBtn = document.createElement('button');
      renameBtn.className = 'conv-row-menu-item';
      renameBtn.textContent = 'Rename';
      renameBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        dropdown.remove();
        const labelEl = row.querySelector('.conv-row-label');
        this._enterRenameMode(row, labelEl, convId);
      });
      dropdown.appendChild(renameBtn);

      const forkBtn = document.createElement('button');
      forkBtn.className = 'conv-row-menu-item';
      forkBtn.textContent = 'Fork from here';
      forkBtn.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        dropdown.remove();
        await this._handleFork(convId);
      });
      dropdown.appendChild(forkBtn);

      const delBtn = document.createElement('button');
      delBtn.className = 'conv-row-menu-item danger';
      delBtn.textContent = 'Delete';
      delBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        dropdown.remove();
        this._handleDelete(convId);
      });
      dropdown.appendChild(delBtn);

      row.appendChild(dropdown);
    }

    _bindGlobalClickToCloseDropdowns() {
      document.addEventListener('click', () => {
        document.querySelectorAll('.conv-row-menu-dropdown').forEach((el) => el.remove());
      });
    }

    _enterRenameMode(row, labelEl, convId) {
      row.dataset.editing = '1';
      labelEl.contentEditable = 'true';
      labelEl.focus();
      // Place cursor at end.
      const range = document.createRange();
      range.selectNodeContents(labelEl);
      range.collapse(false);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);

      const commit = async () => {
        labelEl.contentEditable = 'false';
        row.dataset.editing = '';
        const newLabel = labelEl.textContent.trim();
        const conv = this.conversations.find((c) => c.id === convId);
        if (!conv) return;
        if (!newLabel || newLabel === conv.label) {
          labelEl.textContent = conv.label || '(untitled)';
          return;
        }
        try {
          const resp = await fetch(`/api/conversations/${convId}`, {
            method: 'PATCH',
            credentials: 'same-origin',
            headers: await csrfHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ label: newLabel }),
          });
          if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
          }
          conv.label = newLabel;
          conv.user_renamed = true;
          labelEl.textContent = newLabel;
        } catch (err) {
          console.error('[conv-rail] rename failed', err);
          labelEl.textContent = conv.label || '(untitled)';
        }
      };

      labelEl.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') { ev.preventDefault(); labelEl.blur(); }
        if (ev.key === 'Escape') {
          ev.preventDefault();
          const conv = this.conversations.find((c) => c.id === convId);
          labelEl.textContent = conv ? (conv.label || '(untitled)') : '';
          labelEl.blur();
        }
      }, { once: false });
      labelEl.addEventListener('blur', commit, { once: true });
    }

    async switchTo(convId) {
      if (convId === this.selectedId) return;
      this.selectedId = convId;
      localStorage.setItem(LAST_CONV_KEY, convId);
      // Update selected styling without a full re-render.
      this.list.querySelectorAll('.conv-row').forEach((row) => {
        row.classList.toggle('selected', row.dataset.convId === convId);
      });
      // On mobile, close the rail after a tap.
      if (window.matchMedia('(max-width: 768px)').matches) {
        this.close();
      }
      // Align the header agent picker to this conversation's owning
      // agent so subsequent messages route to the right subprocess.
      // Without this, switching from a Calendar conversation back to
      // an MC one (or vice-versa) would mid-stream-swap the target.
      //
      // Fire the `change` event so chat.js + setAgent + the badge all
      // react consistently. Programmatic picker.value assignment alone
      // does NOT trigger the listeners — that produced a class of bugs
      // where badge/state/list got out of sync after clicking a conv
      // that belonged to a different agent.
      const conv = this.conversations.find((c) => c.id === convId);
      if (conv && conv.agent_id) {
        const picker = document.getElementById('agent-select');
        if (picker && picker.value !== conv.agent_id) {
          picker.value = conv.agent_id;
          picker.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
      if (window.chatUI && typeof window.chatUI.switchConversation === 'function') {
        await window.chatUI.switchConversation(convId);
      }
    }

    async create(label) {
      try {
        // Tag the new conversation with the picker's current agent so
        // it lives in that agent's workspace.
        const picker = document.getElementById('agent-select');
        const agentId = (this.currentAgentId || (picker && picker.value) || '').trim();
        const body = { ...(label ? { label } : {}) };
        if (agentId) body.agent_id = agentId;
        const resp = await fetch('/api/conversations', {
          method: 'POST',
          credentials: 'same-origin',
          headers: await csrfHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          if (resp.status === 503) {
            alert('Conversations feature is disabled. Check PA_WEB_UI_PHASE_2_ENABLED.');
          } else {
            throw new Error(`HTTP ${resp.status}`);
          }
          return;
        }
        const conv = await resp.json();
        this.conversations.unshift({
          id: conv.id,
          agent_id: conv.agent_id,
          label: conv.label,
          parent_conversation_id: conv.parent_conversation_id || null,
          user_renamed: conv.user_renamed,
          last_message_at: null,
          created_at: conv.created_at,
        });
        this.render();
        await this.switchTo(conv.id);
      } catch (err) {
        console.error('[conv-rail] create failed', err);
        alert('Failed to create conversation: ' + err.message);
      }
    }

    _handleDelete(convId) {
      const conv = this.conversations.find((c) => c.id === convId);
      if (!conv) return;
      // Optimistic hide.
      this.hiddenIds.add(convId);
      this.render();

      // If the deleted conv is the selected one, switch away immediately.
      if (this.selectedId === convId) {
        const next = this.conversations.find((c) => !this.hiddenIds.has(c.id));
        if (next) {
          this.switchTo(next.id);
        } else {
          this.selectedId = null;
        }
      }

      new UndoToast({
        text: `Deleted "${conv.label || '(untitled)'}".`,
        onUndo: () => {
          this.hiddenIds.delete(convId);
          this.render();
        },
        onCommit: async () => {
          try {
            const resp = await fetch(`/api/conversations/${convId}`, {
              method: 'DELETE',
              credentials: 'same-origin',
              headers: await csrfHeaders(),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          } catch (err) {
            console.error('[conv-rail] delete failed', err);
            // Surface the failure so the user can retry.
            this.hiddenIds.delete(convId);
            this.render();
            alert('Delete failed: ' + err.message);
            return;
          }
          // Remove from local state entirely.
          this.conversations = this.conversations.filter((c) => c.id !== convId);
          this.hiddenIds.delete(convId);
          this.render();
        },
      });
    }

    async _handleFork(convId) {
      try {
        const resp = await fetch(`/api/conversations/${convId}/fork`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: await csrfHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({}),
        });
        if (resp.status === 409) {
          alert('Can\'t fork while the parent conversation is still streaming.');
          return;
        }
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const conv = await resp.json();
        this.conversations.unshift({
          id: conv.id,
          agent_id: conv.agent_id,
          label: conv.label,
          parent_conversation_id: conv.parent_conversation_id,
          user_renamed: conv.user_renamed,
          last_message_at: null,
          created_at: conv.created_at,
        });
        this.render();
        await this.switchTo(conv.id);
      } catch (err) {
        console.error('[conv-rail] fork failed', err);
        alert('Fork failed: ' + err.message);
      }
    }

    updateLabel(convId, newLabel) {
      const conv = this.conversations.find((c) => c.id === convId);
      if (!conv) return;
      conv.label = newLabel;
      const row = this.list.querySelector(`[data-conv-id="${convId}"] .conv-row-label`);
      if (row) row.textContent = newLabel;
    }

    handleConversationDeleted(convId) {
      // Server-initiated delete (from another tab or a direct API call).
      this.conversations = this.conversations.filter((c) => c.id !== convId);
      this.hiddenIds.delete(convId);
      if (this.selectedId === convId) {
        const next = this.conversations[0];
        this.selectedId = null;
        if (next) this.switchTo(next.id);
      }
      this.render();
    }

    open() {
      this.rail.classList.add('open');
      this.toggle.classList.add('active');
      // Mobile: mutually exclusive with right sidebar.
      if (window.matchMedia('(max-width: 768px)').matches) {
        if (this.taskSidebar) this.taskSidebar.classList.remove('open');
        if (this.taskSidebarToggle) this.taskSidebarToggle.classList.remove('active');
      }
    }

    close() {
      this.rail.classList.remove('open');
      this.toggle.classList.remove('active');
    }

    _bindToggle() {
      if (this.toggle) {
        this.toggle.addEventListener('click', () => {
          if (this.rail.classList.contains('open')) this.close();
          else this.open();
        });
      }
      if (this.closeBtn) {
        this.closeBtn.addEventListener('click', () => this.close());
      }
      // Escape closes the rail on mobile.
      document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape' && this.rail.classList.contains('open')) {
          if (window.matchMedia('(max-width: 768px)').matches) this.close();
        }
      });
      // Auto-close when the user interacts with the main window (chat
      // area, reply box, header controls). Signals: "I've picked a conv
      // and I'm moving on." Capture-phase so we fire before any focus
      // shifts or other handlers. No-op when the rail is already closed.
      const mainContainer = document.querySelector('.page-layout > .container');
      if (mainContainer) {
        mainContainer.addEventListener('mousedown', () => {
          if (this.rail.classList.contains('open')) this.close();
        }, true);
        // Focus events cover keyboard tabbing into main controls.
        mainContainer.addEventListener('focusin', () => {
          if (this.rail.classList.contains('open')) this.close();
        }, true);
      }
    }

    _bindNewButton() {
      if (!this.newBtn) return;
      this.newBtn.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        // Create immediately with auto-timestamp label; let auto-name
        // refine it after the first turn. The user can also rename.
        await this.create(null);
      });
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    window.conversationRail = new ConversationRail();
    // Defer init slightly so chat.js constructor has run first.
    setTimeout(() => window.conversationRail.init(), 50);
  });
})();
