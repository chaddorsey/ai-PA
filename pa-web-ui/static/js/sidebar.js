// Task Review Sidebar — Mission Control for extracted tasks

// CSRF token loader — shared with chat.js via window.__paCsrfReady / __paCsrfToken.
// Idempotent: only fetches if chat.js hasn't already kicked it off.
(function ensurePaCsrfReady() {
  if (window.__paCsrfReady) return;
  window.__paCsrfReady = fetch('/api/csrf-token', { credentials: 'same-origin' })
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      if (data && data.csrf_token) window.__paCsrfToken = data.csrf_token;
      return window.__paCsrfToken;
    })
    .catch((err) => {
      console.warn('[csrf] sidebar token fetch failed', err);
      return null;
    });
})();

async function paCsrfHeaders(extra) {
  const base = Object.assign({}, extra || {});
  try { await window.__paCsrfReady; } catch (_) { /* ignore */ }
  if (window.__paCsrfToken) base['X-CSRF-Token'] = window.__paCsrfToken;
  return base;
}

class TaskSidebar {
  constructor() {
    this.tasks = [];
    this.taskDetails = {};
    this.selectedRefIds = new Set();
    this.openAccordions = new Set();
    this.pollInterval = null;
    this.isOpen = false;
    this.sortable = null;
    this.pendingConfirmRefId = null;
    this.selectedProjectId = null;
    this.selectedProjectName = null;

    // DOM refs
    this.sidebar = document.getElementById('task-sidebar');
    this.toggleTab = document.getElementById('sidebar-toggle');
    this.taskList = document.getElementById('task-list');
    this.badge = document.getElementById('sidebar-badge');
    this.bulkBar = document.getElementById('bulk-actions-bar');
    this.bulkCount = document.querySelector('.bulk-count');

    this.bindEvents();
    this.loadBadgeCount();

    // Tab management
    this.activeTab = 'tasks';
    this.draftsSidebar = null; // Set after DraftsSidebar loads
    this.bindTabEvents();
  }

  bindEvents() {
    this.toggleTab.addEventListener('click', () => this.toggle());
    document.querySelector('.sidebar-close-btn')?.addEventListener('click', () => this.close());

    // Bulk actions
    document.getElementById('bulk-reject-btn')?.addEventListener('click', () => this.bulkReject());
    document.getElementById('bulk-merge-btn')?.addEventListener('click', () => this.openMergeDialog());

    // OF dialog
    document.getElementById('of-dialog-overlay')?.addEventListener('click', (e) => {
      if (e.target === e.currentTarget) this.closeOFDialog();
    });
    document.getElementById('of-dialog-cancel')?.addEventListener('click', () => this.closeOFDialog());
    document.getElementById('of-dialog-cancel-btn')?.addEventListener('click', () => this.closeOFDialog());
    document.getElementById('of-dialog-confirm-btn')?.addEventListener('click', () => this.confirmOFDialog());
    document.getElementById('of-dialog-go-btn')?.addEventListener('click', () => this.confirmAndGo());
    document.getElementById('of-inbox-btn')?.addEventListener('click', () => this.selectProject(null, 'Inbox'));

    // Merge dialog
    document.getElementById('merge-dialog-overlay')?.addEventListener('click', (e) => {
      if (e.target === e.currentTarget) this.closeMergeDialog();
    });
    document.getElementById('merge-dialog-cancel')?.addEventListener('click', () => this.closeMergeDialog());
    document.getElementById('merge-cancel-btn')?.addEventListener('click', () => this.closeMergeDialog());
    document.getElementById('merge-confirm-btn')?.addEventListener('click', () => this.confirmMerge());

    // Escape key closes dialogs/sidebar
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (document.getElementById('draft-edit-overlay')?.classList.contains('visible')) {
          window.draftsSidebar?.closeEditModal();
        } else if (document.getElementById('of-dialog-overlay')?.classList.contains('visible')) {
          this.closeOFDialog();
        } else if (document.getElementById('merge-dialog-overlay')?.classList.contains('visible')) {
          this.closeMergeDialog();
        } else if (this.isOpen) {
          this.close();
        }
      }
    });
  }

  bindTabEvents() {
    document.querySelectorAll('.sidebar-tab').forEach(tab => {
      tab.addEventListener('click', () => this.switchTab(tab.dataset.tab));
    });
  }

  switchTab(tabName) {
    if (tabName === this.activeTab) return;
    this.activeTab = tabName;

    // Update tab UI
    document.querySelectorAll('.sidebar-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.tab === tabName);
    });

    // Update toggle label
    const label = document.getElementById('sidebar-toggle-label');
    label.textContent = tabName === 'tasks' ? 'TASKS' : 'DRAFTS';

    // Switch content
    const taskList = document.getElementById('task-list');
    const draftList = document.getElementById('draft-list');
    const bulkBar = document.getElementById('bulk-actions-bar');

    if (tabName === 'tasks') {
      taskList.style.display = '';
      draftList.style.display = 'none';
      bulkBar.style.display = '';
      this.stopPolling();
      this.loadTasks();
      this.startPolling();
    } else {
      taskList.style.display = 'none';
      draftList.style.display = '';
      bulkBar.style.display = 'none';
      this.stopPolling();
      if (this.draftsSidebar) {
        this.draftsSidebar.loadDrafts();
        this.draftsSidebar.startPolling();
      }
    }
  }

  // ── Sidebar open/close ──

  toggle() {
    this.isOpen ? this.close() : this.open();
  }

  open() {
    this.isOpen = true;
    this.sidebar.classList.add('open');
    this.toggleTab.classList.add('active');
    if (this.activeTab === 'tasks') {
      this.loadTasks();
      this.startPolling();
    } else if (this.draftsSidebar) {
      this.draftsSidebar.loadDrafts();
      this.draftsSidebar.startPolling();
    }
  }

  close() {
    this.isOpen = false;
    this.sidebar.classList.remove('open');
    this.toggleTab.classList.remove('active');
    this.stopPolling();
    if (this.draftsSidebar) this.draftsSidebar.stopPolling();
  }

  startPolling() {
    this.stopPolling();
    this.pollInterval = setInterval(() => this.loadTasks(), 30000);
  }

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }

  // ── Task loading ──

  async loadBadgeCount() {
    try {
      const resp = await fetch('/api/tasks');
      if (!resp.ok) return;
      const data = await resp.json();
      this.updateBadge(data.tasks?.length || 0);
    } catch {
      // Badge count is best-effort
    }
  }

  updateBadge(count) {
    const badge = document.getElementById('sidebar-badge');
    const tabCount = document.getElementById('tasks-tab-count');
    if (count > 0) {
      if (this.activeTab === 'tasks') {
        badge.textContent = count;
        badge.classList.add('visible');
      }
      tabCount.textContent = count;
    } else {
      if (this.activeTab === 'tasks') {
        badge.textContent = '0';
        badge.classList.remove('visible');
      }
      tabCount.textContent = '';
    }
  }

  async loadTasks() {
    try {
      this.taskList.classList.add('loading');
      const resp = await fetch('/api/tasks');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      this.tasks = data.tasks || [];
      this.updateBadge(this.tasks.length);
      this.renderTaskList();
    } catch (e) {
      this.taskList.innerHTML = `<div class="sidebar-error">Failed to load tasks<br><small>${e.message}</small></div>`;
    } finally {
      this.taskList.classList.remove('loading');
    }
  }

  // ── Rendering ──

  renderTaskList() {
    const prevSelected = new Set(this.selectedRefIds);

    if (this.tasks.length === 0) {
      this.taskList.innerHTML = '<div class="sidebar-empty"><span class="empty-icon">&#10003;</span>No pending tasks</div>';
      this.selectedRefIds.clear();
      this.updateBulkBar();
      return;
    }

    this.taskList.innerHTML = '';
    this.tasks.forEach(task => {
      const card = this.buildTaskCard(task);
      if (prevSelected.has(task.ref_id)) {
        card.classList.add('selected');
        card.querySelector('.task-card-checkbox').checked = true;
        this.selectedRefIds.add(task.ref_id);
      }
      // Restore accordion open state
      if (this.openAccordions.has(task.ref_id)) {
        card.classList.add('accordion-open');
        const content = card.querySelector('.task-accordion-content');
        if (this.taskDetails[task.ref_id]) {
          this.renderAccordionContent(content, this.taskDetails[task.ref_id]);
        }
        // Defer maxHeight so DOM has settled
        requestAnimationFrame(() => {
          content.style.maxHeight = content.scrollHeight + 'px';
        });
      }
      this.taskList.appendChild(card);
    });

    // Clean up stale selections and accordions
    const currentRefIds = new Set(this.tasks.map(t => t.ref_id));
    for (const id of this.selectedRefIds) {
      if (!currentRefIds.has(id)) this.selectedRefIds.delete(id);
    }
    for (const id of this.openAccordions) {
      if (!currentRefIds.has(id)) this.openAccordions.delete(id);
    }

    // SortableJS
    if (this.sortable) this.sortable.destroy();
    if (window.Sortable) {
      this.sortable = new Sortable(this.taskList, {
        animation: 200,
        ghostClass: 'task-card-ghost',
        handle: '.task-card-drag',
        easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
      });
    }

    this.updateBulkBar();
  }

  buildTaskCard(task) {
    const card = document.createElement('div');
    card.className = 'task-card';
    card.dataset.refId = task.ref_id;

    const originLabel = task.origin
      ? `<span class="task-origin">${this.escapeHtml(task.origin)}</span>`
      : '';
    const timeLabel = task.extracted_time ? this.formatTime(task.extracted_time) : '';

    // Soft-dedup surfacing: ★ for user-marked ([c]/[;]) tasks (also sorted first
    // by the API), and a ⚠ banner when a candidate likely restates a marked item
    // so it can be weeded right here at confirmation.
    if (task.user_marked) card.classList.add('task-marked');
    const markedBadge = task.user_marked
      ? `<span class="task-marked-badge" title="From your [c]/[;] meeting note — user-marked">★ marked</span>`
      : '';
    const dup = task.potential_duplicate;
    const dupWarn = dup
      ? `<div class="task-dup-warn" title="Likely restates a marked item from the same meeting — review, or reject if redundant">⚠ possible duplicate of marked: &ldquo;${this.escapeHtml((dup.marker_text || '').slice(0, 80))}&rdquo;</div>`
      : '';

    card.innerHTML = `
      <div class="task-card-main">
        <div class="task-card-drag" title="Drag to reorder">&#10495;</div>
        <label class="task-checkbox-wrap">
          <input type="checkbox" class="task-card-checkbox" />
          <span class="task-checkbox-custom"></span>
        </label>
        <div class="task-card-body">
          <div class="task-card-description">${this.escapeHtml(task.description)}</div>
          ${dupWarn}
          <div class="task-card-meta">
            <span class="task-ref-id">${task.ref_id}</span>
            ${markedBadge}
            ${originLabel}
            <span class="task-est-badge${task.estimate_minutes ? '' : ' est-empty'}" data-minutes="${task.estimate_minutes || ''}" title="Estimated duration">⏱ ${task.estimate_minutes ? this.formatEstimate(task.estimate_minutes) : '—'}</span>
            <span class="task-time">${this.escapeHtml(timeLabel)}</span>
          </div>
        </div>
        <div class="task-card-actions">
          <button class="task-btn task-btn-confirm" title="Send to OmniFocus"><svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M6 8h5M9 5.5L11.5 8 9 10.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
          <button class="task-btn task-btn-reject" title="Reject">&#10005;</button>
        </div>
      </div>
      <button class="task-accordion-toggle">
        <span>Details</span>
        <span class="accordion-arrow">&#9662;</span>
      </button>
      <div class="task-accordion-content"></div>
    `;

    // Checkbox
    const cb = card.querySelector('.task-card-checkbox');
    cb.addEventListener('change', () => {
      if (cb.checked) {
        this.selectedRefIds.add(task.ref_id);
        card.classList.add('selected');
      } else {
        this.selectedRefIds.delete(task.ref_id);
        card.classList.remove('selected');
      }
      this.updateBulkBar();
    });

    // Inline edit
    const desc = card.querySelector('.task-card-description');
    desc.addEventListener('click', () => this.startEdit(desc, task.ref_id));

    // Estimate edit
    const estBadge = card.querySelector('.task-est-badge');
    estBadge?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.startEstimateEdit(estBadge, task.ref_id, task);
    });

    // Confirm
    card.querySelector('.task-btn-confirm').addEventListener('click', (e) => {
      e.stopPropagation();
      this.onConfirm(task.ref_id);
    });

    // Reject
    card.querySelector('.task-btn-reject').addEventListener('click', (e) => {
      e.stopPropagation();
      this.onReject(task.ref_id, card);
    });

    // Accordion
    card.querySelector('.task-accordion-toggle').addEventListener('click', () => {
      this.toggleAccordion(task.ref_id, card);
    });

    return card;
  }

  formatTime(isoString) {
    try {
      const d = new Date(isoString);
      const now = new Date();
      const diffMs = now - d;
      const diffHours = diffMs / (1000 * 60 * 60);

      if (diffHours < 1) return `${Math.max(1, Math.floor(diffMs / 60000))}m ago`;
      if (diffHours < 24) return `${Math.floor(diffHours)}h ago`;
      if (diffHours < 48) return 'yesterday';
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch {
      return isoString;
    }
  }

  // ── Inline Edit ──

  startEdit(descEl, refId) {
    if (descEl.contentEditable === 'true') return;

    const original = descEl.textContent;
    descEl.contentEditable = 'true';
    descEl.classList.add('editing');
    descEl.focus();

    // Select all text
    const range = document.createRange();
    range.selectNodeContents(descEl);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);

    const commitEdit = async () => {
      descEl.contentEditable = 'false';
      descEl.classList.remove('editing');
      const newText = descEl.textContent.trim();

      if (newText && newText !== original) {
        try {
          const resp = await fetch(`/api/tasks/${refId}`, {
            method: 'PATCH',
            headers: await paCsrfHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ task_description: newText }),
          });
          if (!resp.ok) {
            descEl.textContent = original;
          }
        } catch {
          descEl.textContent = original;
        }
      } else if (!newText) {
        descEl.textContent = original;
      }
    };

    descEl.addEventListener('blur', commitEdit, { once: true });
    descEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        descEl.blur();
      }
      if (e.key === 'Escape') {
        descEl.textContent = original;
        descEl.blur();
      }
    });
  }

  // ── Accordion ──

  async toggleAccordion(refId, card) {
    const content = card.querySelector('.task-accordion-content');
    const isExpanded = card.classList.contains('accordion-open');

    if (isExpanded) {
      card.classList.remove('accordion-open');
      content.style.maxHeight = '0';
      this.openAccordions.delete(refId);
      return;
    }

    card.classList.add('accordion-open');
    this.openAccordions.add(refId);

    // Always fetch fresh (PACKET INFO may have been added since last load)
    content.innerHTML = '<div class="accordion-loading">Loading details&hellip;</div>';
    content.style.maxHeight = content.scrollHeight + 'px';

    try {
      const resp = await fetch(`/api/tasks/${refId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      this.taskDetails[refId] = data;
    } catch {
      content.innerHTML = '<div class="accordion-error">Failed to load details</div>';
      content.style.maxHeight = content.scrollHeight + 'px';
      return;
    }

    this.renderAccordionContent(content, this.taskDetails[refId]);
    content.style.maxHeight = content.scrollHeight + 'px';
  }

  renderAccordionContent(container, data) {
    const sections = [];

    // PACKET INFO (backtrace results) — top section
    if (data.packet_info) {
      const pi = data.packet_info;
      let html = '<div class="detail-section packet-info-section">';
      html += '<div class="detail-label">Backtrace</div>';

      // Mismatch warning (prominent)
      if (pi.mismatch_warning) {
        html += `<div class="packet-warning">⚠ ${this.escapeHtml(pi.mismatch_warning)}</div>`;
      }

      // Three-node model
      if (pi.direct_action) {
        html += `<div class="packet-node"><span class="packet-node-label">Action:</span> ${this.escapeHtml(pi.direct_action)}</div>`;
      }
      if (pi.artifact_provenance && pi.artifact_provenance !== '(not identified)') {
        html += `<div class="packet-node"><span class="packet-node-label">Artifact:</span> ${this.linkifyUrls(pi.artifact_provenance)}</div>`;
      }
      if (pi.intent_genesis && pi.intent_genesis !== '(not identified)') {
        html += `<div class="packet-node"><span class="packet-node-label">Intent:</span> ${this.escapeHtml(pi.intent_genesis)}</div>`;
      }

      // Context brief
      if (pi.context_brief && pi.context_brief.length > 0) {
        html += '<div class="packet-brief">';
        pi.context_brief.forEach(item => {
          html += `<div class="packet-brief-item">• ${this.escapeHtml(item)}</div>`;
        });
        html += '</div>';
      }

      // Resources
      if (pi.resources && pi.resources.length > 0) {
        html += '<div class="packet-resources"><span class="packet-node-label">Resources:</span>';
        pi.resources.forEach(item => {
          html += `<div class="packet-resource-item">${this.linkifyUrls(item)}</div>`;
        });
        html += '</div>';
      }

      // Related tasks
      if (pi.related_tasks && pi.related_tasks.length > 0) {
        html += '<div class="packet-related"><span class="packet-node-label">Related:</span>';
        pi.related_tasks.forEach(item => {
          html += `<div class="packet-related-item">${this.escapeHtml(item)}</div>`;
        });
        html += '</div>';
      }

      // Knowns / Unknowns
      if (pi.knowns || pi.unknowns) {
        html += '<div class="packet-knowns">';
        if (pi.knowns) {
          pi.knowns.forEach(k => {
            html += `<div class="packet-known">✓ ${this.escapeHtml(k)}</div>`;
          });
        }
        if (pi.unknowns) {
          pi.unknowns.forEach(u => {
            html += `<div class="packet-unknown">? ${this.escapeHtml(u)}</div>`;
          });
        }
        html += '</div>';
      }

      // Agent notes
      if (pi.agent_notes) {
        html += `<div class="packet-notes">${this.escapeHtml(pi.agent_notes)}</div>`;
      }

      html += '</div>';
      sections.push(html);
    }

    if (data.source_reference) {
      const sr = data.source_reference;
      let html = '<div class="detail-section"><div class="detail-label">Source</div>';
      if (sr.origin) html += `<div class="detail-value"><span class="detail-tag">${this.escapeHtml(sr.origin)}</span></div>`;
      if (sr.context) html += `<div class="detail-value">${this.escapeHtml(sr.context)}</div>`;
      if (sr.extracted_by) html += `<div class="detail-value detail-dim">by ${this.escapeHtml(sr.extracted_by)}</div>`;
      html += '</div>';
      sections.push(html);
    }

    if (data.timestamps && data.timestamps.length > 0) {
      let html = '<div class="detail-section"><div class="detail-label">Timestamps</div>';
      data.timestamps.forEach(ts => {
        html += `<div class="detail-value detail-dim">${this.escapeHtml(ts.label)}: ${this.escapeHtml(ts.value)}</div>`;
      });
      html += '</div>';
      sections.push(html);
    }

    if (data.omnifocus) {
      let html = '<div class="detail-section"><div class="detail-label">OmniFocus</div>';
      html += `<div class="detail-value">Status: <span class="detail-tag">${this.escapeHtml(data.omnifocus.status)}</span></div>`;
      if (data.omnifocus.task_id && data.omnifocus.task_id !== 'pending') {
        html += `<div class="detail-value detail-dim">ID: ${this.escapeHtml(data.omnifocus.task_id)}</div>`;
      }
      html += '</div>';
      sections.push(html);
    }

    if (data.source_text) {
      sections.push(`
        <div class="detail-section">
          <div class="detail-label">Source Text</div>
          <div class="detail-source-text">${this.linkifyUrls(data.source_text)}</div>
        </div>
      `);
    }

    container.innerHTML = sections.join('') || '<div class="detail-dim" style="padding:0.75rem">No additional details</div>';
  }

  // ── Confirm flow ──

  async onConfirm(refId) {
    this.pendingConfirmRefId = refId;
    const task = this.tasks.find(t => t.ref_id === refId);

    const overlay = document.getElementById('of-dialog-overlay');
    const input = document.getElementById('of-dialog-task-input');
    input.value = task ? task.description : refId;

    this.selectedProjectId = null;
    this.selectedProjectName = null;
    this.updateOFFooter();

    // Show estimate as read-only check
    const estEl = document.getElementById('of-dialog-estimate');
    if (task && task.estimate_minutes) {
      estEl.textContent = `⏱ ${this.formatEstimate(task.estimate_minutes)} estimated`;
      estEl.style.display = '';
    } else {
      estEl.style.display = 'none';
    }

    overlay.classList.add('visible');
    // Auto-resize textarea to fit content
    input.style.height = 'auto';
    input.style.height = input.scrollHeight + 'px';

    await this.loadOFTree();
  }

  async loadOFTree() {
    const treeContainer = document.getElementById('of-tree');
    treeContainer.innerHTML = '<div class="accordion-loading">Loading OmniFocus projects&hellip;</div>';

    try {
      const resp = await fetch('/api/tasks/omnifocus-tree');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      treeContainer.innerHTML = '';
      if (data.tree && data.tree.length > 0) {
        data.tree.forEach(node => {
          treeContainer.appendChild(this.renderTreeNode(node));
        });
      } else {
        treeContainer.innerHTML = '<div class="detail-dim" style="padding:0.75rem">No projects found</div>';
      }
    } catch (e) {
      treeContainer.innerHTML = `<div class="accordion-error">Failed to load projects: ${e.message}</div>`;
    }
  }

  renderTreeNode(node) {
    const el = document.createElement('div');
    el.className = `of-tree-node of-tree-${node.type}`;

    if (node.type === 'folder') {
      const hasChildren = node.children && node.children.length > 0;
      el.innerHTML = `
        <div class="of-tree-folder-header">
          <span class="of-tree-arrow ${hasChildren ? '' : 'hidden'}">&#9656;</span>
          <span class="of-tree-icon">&#128193;</span>
          <span class="of-tree-name">${this.escapeHtml(node.name)}</span>
        </div>
        <div class="of-tree-children collapsed"></div>
      `;

      if (hasChildren) {
        const childrenContainer = el.querySelector('.of-tree-children');
        node.children.forEach(child => {
          childrenContainer.appendChild(this.renderTreeNode(child));
        });

        el.querySelector('.of-tree-folder-header').addEventListener('click', () => {
          const children = el.querySelector('.of-tree-children');
          const arrow = el.querySelector('.of-tree-arrow');
          children.classList.toggle('collapsed');
          arrow.innerHTML = children.classList.contains('collapsed') ? '&#9656;' : '&#9662;';
        });
      }
    } else {
      // Project
      el.innerHTML = `
        <div class="of-tree-project-row" data-project-id="${this.escapeHtml(node.id)}">
          <span class="of-tree-icon">&#9675;</span>
          <span class="of-tree-name">${this.escapeHtml(node.name)}</span>
        </div>
      `;

      el.querySelector('.of-tree-project-row').addEventListener('click', () => {
        this.selectProject(node.id, node.name);
      });
    }

    return el;
  }

  selectProject(id, name) {
    document.querySelectorAll('.of-tree-project-row.selected').forEach(el => {
      el.classList.remove('selected');
    });
    document.getElementById('of-inbox-btn')?.classList.remove('selected');

    this.selectedProjectId = id;
    this.selectedProjectName = name;

    if (id === null) {
      document.getElementById('of-inbox-btn')?.classList.add('selected');
    } else {
      const row = document.querySelector(`.of-tree-project-row[data-project-id="${id}"]`);
      row?.classList.add('selected');
    }

    this.updateOFFooter();
  }

  updateOFFooter() {
    const label = document.querySelector('.of-selected-project');
    const confirmBtn = document.getElementById('of-dialog-confirm-btn');
    const goBtn = document.getElementById('of-dialog-go-btn');

    if (this.selectedProjectId !== null || this.selectedProjectName === 'Inbox') {
      label.textContent = this.selectedProjectName || 'Inbox';
      label.classList.add('has-selection');
      confirmBtn.disabled = false;
      if (goBtn) goBtn.disabled = false;
    } else {
      label.textContent = 'No project selected';
      label.classList.remove('has-selection');
      confirmBtn.disabled = true;
      if (goBtn) goBtn.disabled = true;
    }
  }

  async createOFTaskFromDialog(rush = false) {
    const refId = this.pendingConfirmRefId;

    // Fetch full passage details for note
    let details = this.taskDetails[refId];
    if (!details) {
      const detResp = await fetch(`/api/tasks/${refId}`);
      if (detResp.ok) details = await detResp.json();
    }

    // Build OmniFocus note from passage context
    const note = this.buildOFNote(refId, details);

    // Read (possibly edited) task name from dialog input
    const taskName = document.getElementById('of-dialog-task-input').value.trim();
    if (!taskName) throw new Error('Task name cannot be empty');

    // If name was edited, persist to backend
    const task = this.tasks.find(t => t.ref_id === refId);
    if (task && taskName !== task.description) {
      await fetch(`/api/tasks/${refId}`, {
        method: 'PATCH',
        headers: await paCsrfHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ task_description: taskName }),
      });
      task.description = taskName;
      const card = this.taskList.querySelector(`.task-card[data-ref-id="${refId}"]`);
      const descEl = card?.querySelector('.task-card-description');
      if (descEl) descEl.textContent = taskName;
    }

    // Create OmniFocus task
    const createResp = await fetch('/api/tasks/omnifocus-create', {
      method: 'POST',
      headers: await paCsrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        name: taskName,
        projectId: this.selectedProjectId,
        note: note,
        estimatedMinutes: task ? task.estimate_minutes : null,
      }),
    });

    if (!createResp.ok) {
      const err = await createResp.json();
      throw new Error(err.error || 'Failed to create OmniFocus task');
    }

    const createData = await createResp.json();
    const omnifocusTaskId = createData.omnifocus_task_id;

    // Transition to confirmed
    const transResp = await fetch(`/api/tasks/${refId}/transition`, {
      method: 'POST',
      headers: await paCsrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        action: 'confirm',
        omnifocus_task_id: omnifocusTaskId,
        rush: rush,
      }),
    });

    if (!transResp.ok) {
      const err = await transResp.json();
      throw new Error(err.error || 'Failed to confirm task');
    }

    return omnifocusTaskId;
  }

  cleanupAfterConfirm(refId) {
    this.closeOFDialog();
    const card = this.taskList.querySelector(`.task-card[data-ref-id="${refId}"]`);
    if (card) this.removeCard(card);
    this.tasks = this.tasks.filter(t => t.ref_id !== refId);
    this.selectedRefIds.delete(refId);
    delete this.taskDetails[refId];
    this.updateBadge(this.tasks.length);
    this.updateBulkBar();
  }

  async confirmOFDialog() {
    const refId = this.pendingConfirmRefId;
    if (!refId) return;

    const confirmBtn = document.getElementById('of-dialog-confirm-btn');
    const goBtn = document.getElementById('of-dialog-go-btn');
    confirmBtn.disabled = true;
    if (goBtn) goBtn.disabled = true;
    confirmBtn.textContent = 'Creating\u2026';

    try {
      await this.createOFTaskFromDialog();
      this.cleanupAfterConfirm(refId);
    } catch (e) {
      alert(`Confirm failed: ${e.message}`);
    } finally {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Confirm';
      if (goBtn) goBtn.disabled = false;
    }
  }

  async confirmAndGo() {
    const refId = this.pendingConfirmRefId;
    if (!refId) return;

    const goBtn = document.getElementById('of-dialog-go-btn');
    const confirmBtn = document.getElementById('of-dialog-confirm-btn');
    goBtn.disabled = true;
    confirmBtn.disabled = true;
    goBtn.textContent = 'Creating\u2026';

    try {
      // Create the OmniFocus task with rush flag — "Add and Go" signals
      // immediate action, so MC prioritizes (skips deeper backtrace, ships fast)
      const omnifocusTaskId = await this.createOFTaskFromDialog(true);

      // Dismiss dialog immediately — queue call runs in background
      this.cleanupAfterConfirm(refId);

      // Fire-and-forget: queue it via the 'next' command (includes OmniFocus sync)
      fetch('/api/tasks/widget-queue', {
        method: 'POST',
        headers: await paCsrfHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ action: 'next', taskId: omnifocusTaskId }),
      }).then(resp => {
        if (resp.ok) return resp.json();
        throw new Error(`Queue HTTP ${resp.status}`);
      }).then(data => {
        const pos = data.position === 0 ? 'first' : 'next up';
        console.log(`[sidebar] Task queued ${pos} in widget:`, data);
      }).catch(err => {
        console.error('[sidebar] Background queue failed:', err);
      });

    } catch (e) {
      alert(`Add & Go failed: ${e.message}`);
    } finally {
      goBtn.textContent = 'Add & Go';
      goBtn.disabled = false;
      confirmBtn.disabled = false;
    }
  }

  buildOFNote(refId, details) {
    if (!details) return `ref_id: ${refId}`;

    const lines = [];
    lines.push(`ref_id: ${refId}`);

    if (details.origin) {
      lines.push(`Origin: ${details.origin}`);
    }

    // Agent Estimate (standalone line for timer widget to pick up)
    // Use the immutable agent_estimate_minutes, fall back to estimate_minutes
    const agentEstMins = details.agent_estimate_minutes || details.estimate_minutes;
    if (agentEstMins) {
      const mins = agentEstMins;
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      const formatted = h > 0
        ? `${h}h ${m < 10 ? '0' : ''}${m}m 00s`
        : `${m}m 00s`;
      lines.push(`Agent Estimate: ${formatted}`);
    }

    // Agent Task Statement (original LLM-formulated description for future RL comparison)
    if (details.task) {
      lines.push(`Agent Task Statement: ${details.task}`);
    }

    // Source Reference
    if (details.source_reference) {
      const sr = details.source_reference;
      lines.push('');
      lines.push('--- Source ---');
      if (sr.type) lines.push(`Type: ${sr.type}`);
      if (sr.context) lines.push(`Context: ${sr.context}`);
      if (sr.reference_id) lines.push(`Reference ID: ${sr.reference_id}`);
    }

    // Source Metadata
    if (details.source_metadata) {
      const sm = details.source_metadata;
      lines.push('');
      lines.push('--- Metadata ---');
      if (sm.timestamp) lines.push(`Timestamp: ${sm.timestamp}`);
      if (sm.from) lines.push(`From: ${sm.from}`);
      if (sm.location) lines.push(`Location: ${sm.location}`);
      if (sm.location_id) lines.push(`Location ID: ${sm.location_id}`);
    }

    // Related URLs
    if (details.related_urls && details.related_urls.length > 0) {
      lines.push('');
      lines.push('--- URLs ---');
      details.related_urls.forEach(u => lines.push(u));
    }

    // Timestamps
    if (details.timestamps && details.timestamps.length > 0) {
      lines.push('');
      lines.push('--- Timestamps ---');
      details.timestamps.forEach(ts => lines.push(`${ts.label}: ${ts.value}`));
    }

    // Source Text
    if (details.source_text) {
      lines.push('');
      lines.push('--- Source Text ---');
      lines.push(details.source_text);
    }

    return lines.join('\n');
  }

  closeOFDialog() {
    document.getElementById('of-dialog-overlay')?.classList.remove('visible');
    const goBtn = document.getElementById('of-dialog-go-btn');
    if (goBtn) {
      goBtn.disabled = true;
      goBtn.textContent = 'Add & Go';
    }
    this.pendingConfirmRefId = null;
    this.selectedProjectId = null;
    this.selectedProjectName = null;
  }

  // ── Reject ──

  async onReject(refId, card) {
    const rejectBtn = card.querySelector('.task-btn-reject');
    rejectBtn.disabled = true;

    try {
      const resp = await fetch(`/api/tasks/${refId}/transition`, {
        method: 'POST',
        headers: await paCsrfHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ action: 'reject' }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || 'Failed to reject');
      }

      this.removeCard(card);
      this.tasks = this.tasks.filter(t => t.ref_id !== refId);
      this.selectedRefIds.delete(refId);
      delete this.taskDetails[refId];
      this.updateBadge(this.tasks.length);
      this.updateBulkBar();

    } catch (e) {
      rejectBtn.disabled = false;
      console.error('Reject failed:', e);
    }
  }

  removeCard(card) {
    card.classList.add('removing');
    card.addEventListener('transitionend', () => card.remove(), { once: true });
    // Fallback if transitionend doesn't fire
    setTimeout(() => { if (card.parentNode) card.remove(); }, 500);
  }

  // ── Bulk actions ──

  updateBulkBar() {
    const count = this.selectedRefIds.size;
    if (count >= 2) {
      this.bulkBar.classList.add('visible');
      this.bulkCount.textContent = `${count} selected`;
    } else {
      this.bulkBar.classList.remove('visible');
    }
  }

  async bulkReject() {
    const refIds = [...this.selectedRefIds];
    const rejectBtn = document.getElementById('bulk-reject-btn');
    rejectBtn.disabled = true;
    rejectBtn.textContent = 'Rejecting\u2026';

    for (const refId of refIds) {
      try {
        const resp = await fetch(`/api/tasks/${refId}/transition`, {
          method: 'POST',
          headers: await paCsrfHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ action: 'reject' }),
        });
        if (resp.ok) {
          const card = this.taskList.querySelector(`.task-card[data-ref-id="${refId}"]`);
          if (card) this.removeCard(card);
          this.tasks = this.tasks.filter(t => t.ref_id !== refId);
          this.selectedRefIds.delete(refId);
          delete this.taskDetails[refId];
        }
      } catch (e) {
        console.error(`Failed to reject ${refId}:`, e);
      }
    }

    this.updateBadge(this.tasks.length);
    this.updateBulkBar();
    rejectBtn.disabled = false;
    rejectBtn.textContent = 'Reject Selected';
  }

  // ── Merge ──

  openMergeDialog() {
    const refIds = [...this.selectedRefIds];
    const descriptions = refIds
      .map(id => this.tasks.find(t => t.ref_id === id)?.description)
      .filter(Boolean);

    const textarea = document.getElementById('merge-description');
    textarea.value = descriptions.join('\n');

    document.getElementById('merge-dialog-overlay')?.classList.add('visible');
    textarea.focus();
  }

  closeMergeDialog() {
    document.getElementById('merge-dialog-overlay')?.classList.remove('visible');
  }

  async confirmMerge() {
    const refIds = [...this.selectedRefIds];
    const description = document.getElementById('merge-description').value.trim();

    if (!description) {
      alert('Please enter a merged task description');
      return;
    }

    const confirmBtn = document.getElementById('merge-confirm-btn');
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Merging\u2026';

    try {
      const resp = await fetch('/api/tasks/merge', {
        method: 'POST',
        headers: await paCsrfHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          ref_ids: refIds,
          merged_task_description: description,
        }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || 'Failed to merge');
      }

      this.closeMergeDialog();
      this.selectedRefIds.clear();
      await this.loadTasks();

    } catch (e) {
      alert(`Merge failed: ${e.message}`);
    } finally {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Merge Tasks';
    }
  }

  // ── Utilities ──

  formatEstimate(minutes) {
    if (!minutes || minutes <= 0) return '—';
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}:${m < 10 ? '0' : ''}${m}`;
  }

  parseEstimate(str) {
    if (!str || str === '—') return null;
    const parts = str.split(':');
    if (parts.length === 2) {
      const h = parseInt(parts[0], 10) || 0;
      const m = parseInt(parts[1], 10) || 0;
      return h * 60 + m;
    }
    const num = parseInt(str, 10);
    return isNaN(num) ? null : num;
  }

  startEstimateEdit(badgeEl, refId, task) {
    if (badgeEl.querySelector('input')) return;

    const originalHtml = badgeEl.innerHTML;
    const current = this.formatEstimate(task.estimate_minutes);
    const displayVal = current === '—' ? '' : current;

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'est-inline-input';
    input.value = displayVal;
    input.placeholder = 'H:MM';
    input.size = 5;

    badgeEl.textContent = '⏱ ';
    badgeEl.appendChild(input);
    input.focus();
    input.select();

    const commit = async () => {
      const parsed = this.parseEstimate(input.value);
      badgeEl.innerHTML = `⏱ ${parsed ? this.formatEstimate(parsed) : '—'}`;
      badgeEl.classList.toggle('est-empty', !parsed);
      badgeEl.dataset.minutes = parsed || '';

      if (parsed !== task.estimate_minutes) {
        task.estimate_minutes = parsed;
        try {
          await fetch(`/api/tasks/${refId}`, {
            method: 'PATCH',
            headers: await paCsrfHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ estimate_minutes: parsed }),
          });
        } catch { /* silent */ }
      }
    };

    input.addEventListener('blur', commit, { once: true });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
      if (e.key === 'Escape') { badgeEl.innerHTML = originalHtml; }
    });
  }

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
      url => {
        // Slack permalinks (channel + DM) are long/ugly; render as "Permalink".
        const display = /slack\.com\/archives\//.test(url) ? 'Permalink' : url;
        return `<a href="${url}" target="_blank" rel="noopener">${display}</a>`;
      }
    );
  }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  window.taskSidebar = new TaskSidebar();
  window.draftsSidebar = new DraftsSidebar(window.taskSidebar);
  window.taskSidebar.draftsSidebar = window.draftsSidebar;

  // Draft edit modal events
  document.getElementById('draft-edit-overlay')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) window.draftsSidebar.closeEditModal();
  });
  document.getElementById('draft-edit-cancel')?.addEventListener('click', () => window.draftsSidebar.closeEditModal());
  document.getElementById('draft-edit-cancel-btn')?.addEventListener('click', () => window.draftsSidebar.closeEditModal());
  document.getElementById('draft-edit-save-btn')?.addEventListener('click', () => window.draftsSidebar.saveDraft());
  document.getElementById('draft-edit-send-btn')?.addEventListener('click', () => window.draftsSidebar.sendFromModal());

  // Load initial draft count
  window.draftsSidebar.loadDrafts();
});
