// Task Review Sidebar — Mission Control for extracted tasks

class TaskSidebar {
  constructor() {
    this.tasks = [];
    this.taskDetails = {};
    this.selectedRefIds = new Set();
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
      this.taskList.appendChild(card);
    });

    // Clean up stale selections
    const currentRefIds = new Set(this.tasks.map(t => t.ref_id));
    for (const id of this.selectedRefIds) {
      if (!currentRefIds.has(id)) this.selectedRefIds.delete(id);
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

    card.innerHTML = `
      <div class="task-card-main">
        <div class="task-card-drag" title="Drag to reorder">&#10495;</div>
        <label class="task-checkbox-wrap">
          <input type="checkbox" class="task-card-checkbox" />
          <span class="task-checkbox-custom"></span>
        </label>
        <div class="task-card-body">
          <div class="task-card-description">${this.escapeHtml(task.description)}</div>
          <div class="task-card-meta">
            <span class="task-ref-id">${task.ref_id}</span>
            ${originLabel}
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
            headers: { 'Content-Type': 'application/json' },
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
      return;
    }

    card.classList.add('accordion-open');

    // Load if not cached
    if (!this.taskDetails[refId]) {
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
    }

    this.renderAccordionContent(content, this.taskDetails[refId]);
    content.style.maxHeight = content.scrollHeight + 'px';
  }

  renderAccordionContent(container, data) {
    const sections = [];

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
          <div class="detail-source-text">${this.escapeHtml(data.source_text)}</div>
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
    const preview = overlay.querySelector('.of-dialog-task-preview');
    preview.textContent = task ? task.description : refId;

    this.selectedProjectId = null;
    this.selectedProjectName = null;
    this.updateOFFooter();

    overlay.classList.add('visible');
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

    if (this.selectedProjectId !== null || this.selectedProjectName === 'Inbox') {
      label.textContent = this.selectedProjectName || 'Inbox';
      label.classList.add('has-selection');
      confirmBtn.disabled = false;
    } else {
      label.textContent = 'No project selected';
      label.classList.remove('has-selection');
      confirmBtn.disabled = true;
    }
  }

  async confirmOFDialog() {
    const refId = this.pendingConfirmRefId;
    if (!refId) return;

    const confirmBtn = document.getElementById('of-dialog-confirm-btn');
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Creating\u2026';

    try {
      // 1. Create OmniFocus task
      const task = this.tasks.find(t => t.ref_id === refId);
      const createResp = await fetch('/api/tasks/omnifocus-create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: task ? task.description : refId,
          projectId: this.selectedProjectId,
        }),
      });

      if (!createResp.ok) {
        const err = await createResp.json();
        throw new Error(err.error || 'Failed to create OmniFocus task');
      }

      const createData = await createResp.json();
      const omnifocusTaskId = createData.omnifocus_task_id;

      // 2. Transition to confirmed
      const transResp = await fetch(`/api/tasks/${refId}/transition`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'confirm',
          omnifocus_task_id: omnifocusTaskId,
        }),
      });

      if (!transResp.ok) {
        const err = await transResp.json();
        throw new Error(err.error || 'Failed to confirm task');
      }

      // 3. Close dialog & remove card
      this.closeOFDialog();
      const card = this.taskList.querySelector(`.task-card[data-ref-id="${refId}"]`);
      if (card) this.removeCard(card);

      this.tasks = this.tasks.filter(t => t.ref_id !== refId);
      this.selectedRefIds.delete(refId);
      delete this.taskDetails[refId];
      this.updateBadge(this.tasks.length);
      this.updateBulkBar();

    } catch (e) {
      alert(`Confirm failed: ${e.message}`);
    } finally {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Confirm';
    }
  }

  closeOFDialog() {
    document.getElementById('of-dialog-overlay')?.classList.remove('visible');
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
        headers: { 'Content-Type': 'application/json' },
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
          headers: { 'Content-Type': 'application/json' },
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
        headers: { 'Content-Type': 'application/json' },
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

  escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
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
