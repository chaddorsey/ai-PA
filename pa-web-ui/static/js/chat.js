// PA Web UI - Chat functionality with streaming feedback

// Slash command to agent ID mapping for explicit routing
// Usage: /calendar What's on my schedule? → routes to Calendar Agent
const SLASH_COMMAND_MAP = {
    // Direct agent mappings
    'calendar': 'agent-892a2d58-b9f6-4baf-84f3-c431fe46487d',
    'cal': 'agent-892a2d58-b9f6-4baf-84f3-c431fe46487d',
    'task': 'agent-dd15479e-6543-400e-8463-b2a48b13cd4a',
    'tasks': 'agent-dd15479e-6543-400e-8463-b2a48b13cd4a',
    'omnifocus': 'agent-dd15479e-6543-400e-8463-b2a48b13cd4a',
    'main': 'agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a',
    'pulse': 'agent-2ed14ef4-6289-453a-ae27-290b6ed196b8',
    'email': 'agent-b4928949-8012-4436-a3c7-a9e510785147',

    // Domain aliases that route to Pulse Agent
    'slack': 'agent-2ed14ef4-6289-453a-ae27-290b6ed196b8',
    'jira': 'agent-2ed14ef4-6289-453a-ae27-290b6ed196b8',
    'docs': 'agent-2ed14ef4-6289-453a-ae27-290b6ed196b8',
    'documents': 'agent-2ed14ef4-6289-453a-ae27-290b6ed196b8',
    'google-docs': 'agent-2ed14ef4-6289-453a-ae27-290b6ed196b8',
    'drive': 'agent-2ed14ef4-6289-453a-ae27-290b6ed196b8',
};

// Slash command to friendly agent name (for display)
const SLASH_COMMAND_NAMES = {
    'calendar': 'Calendar Agent',
    'cal': 'Calendar Agent',
    'task': 'Task Agent',
    'tasks': 'Task Agent',
    'omnifocus': 'Task Agent',
    'main': 'Main Agent',
    'pulse': 'Pulse Agent',
    'email': 'Email Agent',
    'slack': 'Pulse Agent',
    'jira': 'Pulse Agent',
    'docs': 'Pulse Agent',
    'documents': 'Pulse Agent',
    'google-docs': 'Pulse Agent',
    'drive': 'Pulse Agent',
};

// Tool name to friendly status message mapping
const TOOL_STATUS_MAP = {
    // Calendar tools
    'calendar_search': 'Searching calendars...',
    'search_calendar': 'Searching calendars...',
    'get_calendar_events': 'Checking calendar...',
    'create_calendar_event': 'Creating event...',
    'schedule_meeting': 'Scheduling meeting...',
    'find_availability': 'Finding available times...',

    // Task tools
    'get_tasks': 'Fetching tasks...',
    'create_task': 'Creating task...',
    'omnifocus_search': 'Searching OmniFocus...',
    'get_omnifocus_tasks': 'Checking tasks...',

    // Memory tools
    'archival_memory_search': 'Searching memory...',
    'archival_memory_insert': 'Saving to memory...',
    'core_memory_append': 'Updating memory...',
    'core_memory_replace': 'Updating memory...',
    'conversation_search': 'Searching conversations...',

    // Slack tools
    'send_slack_message': 'Sending Slack message...',
    'search_slack': 'Searching Slack...',
    'get_slack_channels': 'Getting channels...',

    // Document tools
    'search_documents': 'Searching documents...',
    'get_document': 'Fetching document...',

    // Web/general tools
    'web_search': 'Searching the web...',
    'send_message': 'Composing response...',
};

class ChatUI {
    constructor() {
        this.messagesContainer = document.getElementById('messages');
        this.messageInput = document.getElementById('message-input');
        this.sendBtn = document.getElementById('send-btn');
        this.agentSelect = document.getElementById('agent-select');
        this.replyIndicator = document.getElementById('reply-indicator');
        this.inputArea = document.querySelector('.input-area');

        this.sessionId = this.getOrCreateSessionId();
        this.statusIndicator = null;

        // Thread tracking for contextual routing and threaded UI
        this.threads = new Map(); // request_id -> { userMessage, agentId, agentName, response, status, element }

        // Track in-flight requests for concurrent message handling
        this.inFlightRequests = new Set(); // Set of request_ids currently streaming

        // Reply mode - when set, next message routes to this agent AND appends to card
        this.replyToAgent = null; // { agentId, agentName }
        this.replyToCard = null;  // The card element to append to when in reply mode

        // Configure marked for safe rendering
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,      // Convert \n to <br>
                gfm: true,         // GitHub Flavored Markdown
                pedantic: false,   // Don't be strict about markdown spec
                smartLists: true,  // Better list handling
            });
        }

        this.setupEventListeners();
        this.loadAgents();
        this.loadConversationHistory();
    }

    getOrCreateSessionId() {
        const STORAGE_KEY = 'pa_chat_session_id';
        let sessionId = localStorage.getItem(STORAGE_KEY);
        if (!sessionId) {
            sessionId = this.generateSessionId();
            localStorage.setItem(STORAGE_KEY, sessionId);
        }
        return sessionId;
    }

    generateSessionId() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    formatTimestamp(date = new Date()) {
        const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        const dayName = days[date.getDay()];
        const month = date.getMonth() + 1;
        const day = date.getDate();
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        return `${month}/${day} ${dayName} - ${hours}:${minutes}`;
    }

    setupEventListeners() {
        this.sendBtn.addEventListener('click', () => this.sendMessage());

        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
            // Escape key clears reply mode
            if (e.key === 'Escape' && this.replyToAgent) {
                this.clearReplyMode();
            }
        });

        // Auto-resize textarea
        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 150) + 'px';
        });

        // Clear reply button
        const clearReplyBtn = this.replyIndicator?.querySelector('.clear-reply-btn');
        if (clearReplyBtn) {
            clearReplyBtn.addEventListener('click', () => this.clearReplyMode());
        }
    }

    setReplyMode(agentId, agentName, cardElement) {
        this.replyToAgent = { agentId, agentName };
        this.replyToCard = cardElement;
        if (this.replyIndicator) {
            this.replyIndicator.classList.add('active');
            this.replyIndicator.querySelector('.agent-name').textContent = agentName;
        }
        if (this.inputArea) {
            this.inputArea.classList.add('reply-mode');
        }
        this.messageInput.focus();
    }

    clearReplyMode() {
        this.replyToAgent = null;
        this.replyToCard = null;
        if (this.replyIndicator) {
            this.replyIndicator.classList.remove('active');
        }
        if (this.inputArea) {
            this.inputArea.classList.remove('reply-mode');
        }
    }

    async loadAgents() {
        try {
            const response = await fetch('/api/agents');
            if (response.ok) {
                const data = await response.json();
                this.populateAgentSelect(data.agents);
            }
        } catch (error) {
            console.error('Failed to load agents:', error);
            this.agentSelect.innerHTML = '<option value="">Default Agent</option>';
        }
    }

    populateAgentSelect(agents) {
        this.agentSelect.innerHTML = agents.map(agent =>
            `<option value="${agent.id}">${agent.name}</option>`
        ).join('');
    }

    async loadConversationHistory() {
        try {
            const response = await fetch(`/api/conversations/${this.sessionId}`);
            if (!response.ok) return;

            const data = await response.json();
            const conversations = data.conversations || [];

            if (conversations.length === 0) return;

            // Group messages by request_id to reconstruct threads
            const threadsByRequestId = new Map();
            const orphanMessages = [];

            for (const msg of conversations) {
                const requestId = msg.metadata?.request_id;
                if (requestId) {
                    if (!threadsByRequestId.has(requestId)) {
                        threadsByRequestId.set(requestId, []);
                    }
                    threadsByRequestId.get(requestId).push(msg);
                } else {
                    orphanMessages.push(msg);
                }
            }

            // Render each thread as a card
            for (const [requestId, messages] of threadsByRequestId) {
                const userMsg = messages.find(m => m.role === 'user');
                const assistantMsg = messages.find(m => m.role === 'assistant');

                if (userMsg) {
                    this.renderHistoryThread(
                        userMsg.message,
                        assistantMsg?.message || '',
                        assistantMsg?.agent_name || userMsg.agent_name || 'Assistant',
                        assistantMsg?.agent_id || userMsg.agent_id || '',
                        requestId,
                        userMsg.created_at,
                        assistantMsg?.created_at
                    );
                }
            }

            // Render any orphan messages (shouldn't happen often)
            for (const msg of orphanMessages) {
                if (msg.role === 'user') {
                    this.renderHistoryThread(msg.message, '', 'Assistant', '', null, msg.created_at, null);
                }
            }

            this.scrollToBottom();
        } catch (error) {
            console.error('Failed to load conversation history:', error);
        }
    }

    renderHistoryThread(userMessage, assistantResponse, agentName, agentId, requestId, userTimestamp = null, assistantTimestamp = null) {
        const card = document.createElement('div');
        card.className = 'thread-card';
        if (requestId) card.dataset.requestId = requestId;
        if (agentId) card.dataset.agentId = agentId;
        if (agentName) card.dataset.agentName = agentName;

        const hasResponse = assistantResponse && assistantResponse.trim().length > 0;
        const userTime = userTimestamp ? this.formatTimestamp(new Date(userTimestamp)) : '';
        const assistantTime = assistantTimestamp ? this.formatTimestamp(new Date(assistantTimestamp)) : '';

        card.innerHTML = `
            <div class="thread-user-message">
                <span class="user-text">${this.escapeHtml(userMessage)}</span>
                ${userTime ? `<span class="message-timestamp">${userTime}</span>` : ''}
            </div>
            ${hasResponse ? `
                <div class="thread-response" style="display: block;">
                    <div class="response-header">
                        <div class="agent-header">
                            <span class="agent-icon">🤖</span>
                            <span class="agent-name">${this.escapeHtml(agentName)}</span>
                        </div>
                        <div class="response-feedback">
                            <div class="feedback-buttons">
                                <button class="feedback-btn thumbs-up" title="Good response">👍</button>
                                <button class="feedback-btn thumbs-down" title="Poor response">👎</button>
                            </div>
                            <div class="agent-correction">
                                <a href="#" class="agent-correction-link">Agent?</a>
                                <div class="agent-dropdown" style="display: none;">
                                    <select class="intended-agent-select">
                                        <option value="">Select intended agent...</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="response-content">${this.renderMarkdown(assistantResponse)}</div>
                    ${assistantTime ? `<span class="message-timestamp response-timestamp">${assistantTime}</span>` : ''}
                </div>
            ` : `
                <div class="thread-status">
                    <span class="status-text">No response recorded</span>
                </div>
            `}
            <div class="thread-footer" style="display: ${hasResponse ? 'flex' : 'none'};">
                <button class="reply-btn">Reply</button>
            </div>
        `;

        // Wire up reply button and feedback if there's a response
        if (hasResponse && agentId) {
            const replyBtn = card.querySelector('.reply-btn');
            if (replyBtn) {
                replyBtn.addEventListener('click', () => {
                    this.setReplyMode(agentId, agentName, card);
                });
            }
            // Wire up feedback buttons for the initial response
            this.setupFeedbackButtons(card, card.querySelector(':scope > .thread-response'));
        }

        this.messagesContainer.appendChild(card);
    }

    /**
     * Parse slash command from message.
     * Returns { command, agentId, agentName, cleanMessage } or null if no command.
     * Example: "/calendar What's on my schedule?" returns:
     *   { command: 'calendar', agentId: '...', agentName: 'Calendar Agent', cleanMessage: "What's on my schedule?" }
     */
    parseSlashCommand(message) {
        const match = message.match(/^\/([a-zA-Z0-9-]+)\s*(.*)/s);
        if (!match) return null;

        const command = match[1].toLowerCase();
        const cleanMessage = match[2].trim();

        const agentId = SLASH_COMMAND_MAP[command];
        if (!agentId) return null; // Unknown command, treat as normal message

        return {
            command,
            agentId,
            agentName: SLASH_COMMAND_NAMES[command] || 'Agent',
            cleanMessage: cleanMessage || command, // If no message after command, use command as message
        };
    }

    async sendMessage() {
        const rawMessage = this.messageInput.value.trim();
        if (!rawMessage) return;

        // Check for slash command routing
        const slashCommand = this.parseSlashCommand(rawMessage);
        const message = slashCommand ? slashCommand.cleanMessage : rawMessage;
        const displayMessage = rawMessage; // Show original message with slash command in UI

        // Priority: slash command > reply mode > dropdown > auto-routing
        let agentId;
        if (slashCommand) {
            agentId = slashCommand.agentId;
        } else if (this.replyToAgent?.agentId) {
            agentId = this.replyToAgent.agentId;
        } else {
            agentId = this.agentSelect.value || null;
        }

        // Track thread position and parent for learning signals
        let threadPosition = 0;
        let parentRequestId = null;

        // Determine whether to append to existing card or create new one
        let threadCard;
        if (this.replyToCard) {
            // Reply mode: append to existing card
            threadCard = this.replyToCard;
            parentRequestId = threadCard.dataset.requestId;
            // Count existing exchanges to determine position
            threadPosition = threadCard.querySelectorAll('.thread-followup-container').length + 1;
            this.appendExchangeToCard(threadCard, displayMessage);
        } else {
            // Normal mode: create new card
            threadCard = this.createThreadCard(displayMessage);
        }

        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';

        // Clear reply mode after sending
        this.clearReplyMode();

        // Build learning signal data
        const learningSignals = {
            slashCommand: slashCommand?.command || null,
            originalMessage: slashCommand ? rawMessage : null,
            threadPosition,
            parentRequestId,
        };

        // Fire off the stream request without blocking
        this.processStreamRequest(message, agentId, threadCard, learningSignals);

        // Keep focus on input for next message
        this.messageInput.focus();
    }

    appendExchangeToCard(card, userMessage) {
        // Hide the current reply button (will show new one when response completes)
        const existingFooter = card.querySelector('.thread-footer');
        if (existingFooter) {
            existingFooter.style.display = 'none';
        }

        // Remove active-exchange marker from any previous exchange
        card.querySelectorAll('.active-exchange').forEach(el => el.classList.remove('active-exchange'));

        // Add a divider and new user message (indented as thread content)
        const timestamp = this.formatTimestamp();
        const exchangeHtml = `
            <div class="thread-exchange-divider"></div>
            <div class="thread-followup-container">
                <div class="thread-user-followup">
                    <span class="user-text">${this.escapeHtml(userMessage)}</span>
                    <span class="message-timestamp">${timestamp}</span>
                </div>
                <div class="thread-status active-exchange">
                    <div class="dots">
                        <div class="dot"></div>
                        <div class="dot"></div>
                        <div class="dot"></div>
                    </div>
                    <span class="status-text">Connecting...</span>
                </div>
                <div class="thread-followup-response active-exchange" style="display: none;">
                    <div class="followup-response-header">
                        <div class="response-feedback">
                            <div class="feedback-buttons">
                                <button class="feedback-btn thumbs-up" title="Good response">👍</button>
                                <button class="feedback-btn thumbs-down" title="Poor response">👎</button>
                            </div>
                            <div class="agent-correction">
                                <a href="#" class="agent-correction-link">Agent?</a>
                                <div class="agent-dropdown" style="display: none;">
                                    <select class="intended-agent-select">
                                        <option value="">Select intended agent...</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="response-content"></div>
                    <span class="message-timestamp response-timestamp"></span>
                </div>
            </div>
        `;

        // Insert before the footer
        if (existingFooter) {
            existingFooter.insertAdjacentHTML('beforebegin', exchangeHtml);
        } else {
            card.insertAdjacentHTML('beforeend', exchangeHtml);
        }

        // Mark card as streaming again
        card.classList.add('streaming');
        this.scrollToBottom();
    }

    async processStreamRequest(message, agentId, threadCard, learningSignals = {}) {
        // Generate a temporary ID until we get the real one from routing
        const tempId = `temp-${Date.now()}`;
        this.inFlightRequests.add(tempId);

        try {
            await this.streamResponse(message, agentId, threadCard, tempId, learningSignals);
        } catch (error) {
            console.error('Stream error:', error);
            this.updateThreadCardError(threadCard, 'Failed to get response');
        } finally {
            this.inFlightRequests.delete(tempId);
        }
    }

    createThreadCard(userMessage) {
        const card = document.createElement('div');
        card.className = 'thread-card streaming';
        const timestamp = this.formatTimestamp();
        card.innerHTML = `
            <div class="thread-user-message">
                <span class="user-text">${this.escapeHtml(userMessage)}</span>
                <span class="message-timestamp">${timestamp}</span>
            </div>
            <div class="thread-status">
                <div class="dots">
                    <div class="dot"></div>
                    <div class="dot"></div>
                    <div class="dot"></div>
                </div>
                <span class="status-text">Connecting...</span>
            </div>
            <div class="thread-response" style="display: none;">
                <div class="response-header">
                    <div class="agent-header">
                        <span class="agent-icon">🤖</span>
                        <span class="agent-name"></span>
                    </div>
                    <div class="response-feedback">
                        <div class="feedback-buttons">
                            <button class="feedback-btn thumbs-up" title="Good response">👍</button>
                            <button class="feedback-btn thumbs-down" title="Poor response">👎</button>
                        </div>
                        <div class="agent-correction">
                            <a href="#" class="agent-correction-link">Agent?</a>
                            <div class="agent-dropdown" style="display: none;">
                                <select class="intended-agent-select">
                                    <option value="">Select intended agent...</option>
                                </select>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="response-content"></div>
                <span class="message-timestamp response-timestamp"></span>
            </div>
            <div class="thread-footer">
                <button class="reply-btn">Reply</button>
            </div>
        `;

        this.messagesContainer.appendChild(card);
        this.scrollToBottom();
        return card;
    }

    updateThreadCardStatus(card, statusText) {
        // Check for active follow-up exchange first, then fall back to initial status
        const activeStatus = card.querySelector('.thread-status.active-exchange');
        // Initial status is a direct child of the card (not inside a container)
        const initialStatus = card.querySelector(':scope > .thread-status');
        const statusEl = activeStatus || initialStatus;

        if (statusEl) {
            const textEl = statusEl.querySelector('.status-text');
            if (textEl) textEl.textContent = statusText;
        }
    }

    updateThreadCardResponse(card, agentName, content) {
        // Check for active follow-up exchange first
        const activeStatus = card.querySelector('.thread-status.active-exchange');
        const activeResponse = card.querySelector('.thread-followup-response.active-exchange');
        const timestamp = this.formatTimestamp();

        if (activeStatus && activeResponse) {
            // This is a follow-up response - no agent name needed
            activeStatus.style.display = 'none';
            activeResponse.style.display = 'block';
            activeResponse.querySelector('.response-content').innerHTML = this.renderMarkdown(content);
            const timestampEl = activeResponse.querySelector('.response-timestamp');
            if (timestampEl) timestampEl.textContent = timestamp;
        } else {
            // Initial response - use direct child selectors to avoid matching follow-up elements
            const initialStatus = card.querySelector(':scope > .thread-status');
            const initialResponse = card.querySelector(':scope > .thread-response');

            if (initialStatus) initialStatus.style.display = 'none';
            if (initialResponse) {
                initialResponse.style.display = 'block';
                const agentNameEl = initialResponse.querySelector('.agent-name');
                if (agentNameEl) agentNameEl.textContent = agentName;
                initialResponse.querySelector('.response-content').innerHTML = this.renderMarkdown(content);
                const timestampEl = initialResponse.querySelector('.response-timestamp');
                if (timestampEl) timestampEl.textContent = timestamp;
            }
        }
    }

    updateThreadCardError(card, errorMessage) {
        // Check for active follow-up exchange first
        const activeStatus = card.querySelector('.thread-status.active-exchange');
        const activeResponse = card.querySelector('.thread-followup-response.active-exchange');

        if (activeStatus && activeResponse) {
            // Error in follow-up response
            activeStatus.style.display = 'none';
            activeResponse.style.display = 'block';
            activeResponse.querySelector('.response-content').innerHTML = `<span style="color: var(--accent);">${this.escapeHtml(errorMessage)}</span>`;
        } else {
            // Error in initial response - use direct child selectors
            const initialStatus = card.querySelector(':scope > .thread-status');
            const initialResponse = card.querySelector(':scope > .thread-response');

            if (initialStatus) initialStatus.style.display = 'none';
            if (initialResponse) {
                initialResponse.style.display = 'block';
                const agentNameEl = initialResponse.querySelector('.agent-name');
                if (agentNameEl) agentNameEl.textContent = 'Error';
                initialResponse.querySelector('.response-content').innerHTML = `<span style="color: var(--accent);">${this.escapeHtml(errorMessage)}</span>`;
            }
        }

        card.classList.remove('streaming');
    }

    finalizeThreadCard(card, agentId, agentName) {
        card.classList.remove('streaming');
        card.dataset.agentId = agentId;
        card.dataset.agentName = agentName;

        // Hide ALL status indicators (tool call spinners, etc.)
        card.querySelectorAll('.thread-status').forEach(el => {
            el.style.display = 'none';
        });

        // Show the footer and wire up reply button
        const footer = card.querySelector('.thread-footer');
        if (footer) {
            footer.style.display = 'flex';
            const replyBtn = footer.querySelector('.reply-btn');
            if (replyBtn) {
                // Remove old listeners by cloning
                const newReplyBtn = replyBtn.cloneNode(true);
                replyBtn.parentNode.replaceChild(newReplyBtn, replyBtn);
                newReplyBtn.addEventListener('click', () => {
                    this.setReplyMode(agentId, agentName, card);
                });
            }
        }

        // Wire up feedback buttons for the active response
        // Check for active follow-up first, then initial response
        const activeFollowup = card.querySelector('.thread-followup-response.active-exchange');
        const initialResponse = card.querySelector(':scope > .thread-response');
        const targetResponse = activeFollowup || initialResponse;

        if (targetResponse) {
            this.setupFeedbackButtons(card, targetResponse);
        }
    }

    setupFeedbackButtons(card, responseEl = null) {
        const requestId = card.dataset.requestId;
        const agentId = card.dataset.agentId;
        const agentName = card.dataset.agentName;

        // Use responseEl if provided, otherwise use card (for backward compat)
        const container = responseEl || card;

        // Thumbs up button
        const thumbsUp = container.querySelector('.thumbs-up');
        if (thumbsUp && !thumbsUp.dataset.wired) {
            thumbsUp.dataset.wired = 'true';
            thumbsUp.addEventListener('click', () => {
                this.sendFeedback(requestId, 'thumbs_up', agentId, agentName);
                thumbsUp.classList.add('selected');
                const thumbsDown = container.querySelector('.thumbs-down');
                if (thumbsDown) thumbsDown.classList.remove('selected');
            });
        }

        // Thumbs down button
        const thumbsDown = container.querySelector('.thumbs-down');
        if (thumbsDown && !thumbsDown.dataset.wired) {
            thumbsDown.dataset.wired = 'true';
            thumbsDown.addEventListener('click', () => {
                this.sendFeedback(requestId, 'thumbs_down', agentId, agentName);
                thumbsDown.classList.add('selected');
                if (thumbsUp) thumbsUp.classList.remove('selected');
            });
        }

        // Agent correction link
        const agentLink = container.querySelector('.agent-correction-link');
        const agentDropdown = container.querySelector('.agent-dropdown');
        const agentSelect = container.querySelector('.intended-agent-select');

        if (agentLink && agentDropdown && agentSelect && !agentLink.dataset.wired) {
            agentLink.dataset.wired = 'true';
            // Populate dropdown with agents
            this.populateAgentDropdown(agentSelect);

            agentLink.addEventListener('click', (e) => {
                e.preventDefault();
                const isVisible = agentDropdown.style.display !== 'none';
                agentDropdown.style.display = isVisible ? 'none' : 'block';
            });

            agentSelect.addEventListener('change', () => {
                const selectedOption = agentSelect.options[agentSelect.selectedIndex];
                if (selectedOption.value) {
                    this.sendFeedback(
                        requestId,
                        'agent_correction',
                        agentId,
                        agentName,
                        selectedOption.value,
                        selectedOption.text
                    );
                    agentDropdown.style.display = 'none';
                    agentLink.textContent = `→ ${selectedOption.text}`;
                    agentLink.classList.add('corrected');
                }
            });
        }
    }

    populateAgentDropdown(selectEl) {
        // Use cached agents from the main dropdown
        const mainSelect = this.agentSelect;
        if (mainSelect) {
            selectEl.innerHTML = '<option value="">Select intended agent...</option>';
            for (const option of mainSelect.options) {
                const newOption = document.createElement('option');
                newOption.value = option.value;
                newOption.text = option.text;
                selectEl.appendChild(newOption);
            }
        }
    }

    async sendFeedback(requestId, feedbackType, actualAgentId, actualAgentName, intendedAgentId = null, intendedAgentName = null) {
        try {
            await fetch('/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    request_id: requestId,
                    feedback_type: feedbackType,
                    actual_agent_id: actualAgentId,
                    actual_agent_name: actualAgentName,
                    intended_agent_id: intendedAgentId,
                    intended_agent_name: intendedAgentName,
                })
            });
            console.log(`Feedback recorded: ${feedbackType}`);
        } catch (error) {
            console.error('Failed to record feedback:', error);
        }
    }

    showStatusIndicator(text = 'Thinking...') {
        this.removeStatusIndicator();

        const indicator = document.createElement('div');
        indicator.className = 'status-indicator';
        indicator.innerHTML = `
            <div class="dots">
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
            </div>
            <span class="status-text">${text}</span>
        `;
        this.messagesContainer.appendChild(indicator);
        this.statusIndicator = indicator;
        this.scrollToBottom();
    }

    updateStatusIndicator(text) {
        if (this.statusIndicator) {
            const statusText = this.statusIndicator.querySelector('.status-text');
            if (statusText) {
                statusText.textContent = text;
            }
        }
    }

    removeStatusIndicator() {
        if (this.statusIndicator) {
            this.statusIndicator.remove();
            this.statusIndicator = null;
        }
    }

    async streamResponse(message, explicitAgentId, threadCard, tempId, learningSignals = {}) {
        const response = await fetch('/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                agent_id: explicitAgentId,
                session_id: this.sessionId,
                // Learning signals for improving routing
                slash_command: learningSignals.slashCommand,
                original_message: learningSignals.originalMessage,
                thread_position: learningSignals.threadPosition || 0,
                parent_request_id: learningSignals.parentRequestId,
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let content = '';
        let agentName = '';
        let agentId = '';
        let requestId = null;
        let hasReceivedContent = false;
        let toolCallsMade = [];  // Track tool calls for completion message

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const event = JSON.parse(line.slice(6));

                        if (event.type === 'routing') {
                            agentName = event.agent_name;
                            agentId = event.agent_id;
                            requestId = event.request_id;

                            // Replace temp ID with real request ID in tracking
                            if (tempId && requestId) {
                                this.inFlightRequests.delete(tempId);
                                this.inFlightRequests.add(requestId);
                            }

                            // Create thread entry
                            if (requestId) {
                                this.threads.set(requestId, {
                                    userMessage: message,
                                    agentId: agentId,
                                    agentName: agentName,
                                    response: '',
                                    status: 'streaming',
                                    createdAt: new Date(),
                                    element: threadCard
                                });
                                threadCard.dataset.requestId = requestId;
                            }

                            this.updateThreadCardStatus(threadCard, `Connected to ${agentName}...`);
                        } else if (event.type === 'tool_call') {
                            // Show contextual status for tool calls
                            const toolName = event.tool || 'unknown';
                            toolCallsMade.push(toolName);  // Track for completion message
                            // Skip status update for internal/coordination tools
                            if (toolName !== 'report_refs' && toolName !== 'send_message') {
                                const statusText = TOOL_STATUS_MAP[toolName] || `Running ${toolName}...`;
                                this.updateThreadCardStatus(threadCard, statusText);
                            }
                        } else if (event.type === 'text') {
                            hasReceivedContent = true;
                            content += event.content;
                            this.updateThreadCardResponse(threadCard, agentName, content);

                            // Update thread response
                            if (requestId && this.threads.has(requestId)) {
                                this.threads.get(requestId).response = content;
                            }
                        } else if (event.type === 'token') {
                            hasReceivedContent = true;
                            content += event.token;
                            this.updateThreadCardResponse(threadCard, agentName, content);

                            // Update thread response
                            if (requestId && this.threads.has(requestId)) {
                                this.threads.get(requestId).response = content;
                            }
                        } else if (event.type === 'done') {
                            // Mark thread as complete and finalize card
                            if (requestId && this.threads.has(requestId)) {
                                this.threads.get(requestId).status = 'complete';
                            }
                            // Remove from in-flight tracking
                            if (requestId) {
                                this.inFlightRequests.delete(requestId);
                            }
                            // If no text content but tools were called, show completion message
                            if (!hasReceivedContent && toolCallsMade.length > 0) {
                                const displayTools = toolCallsMade.filter(t => t !== 'report_refs' && t !== 'send_message');
                                if (displayTools.length > 0) {
                                    this.updateThreadCardResponse(threadCard, agentName, `✓ Completed: ${displayTools.join(', ')}`);
                                } else {
                                    this.updateThreadCardResponse(threadCard, agentName, '✓ Done');
                                }
                            }
                            this.finalizeThreadCard(threadCard, agentId, agentName);
                        } else if (event.type === 'ping') {
                            // Keepalive ping from server - ignore but keep connection alive
                            // This prevents frontend timeout during long operations
                        } else if (event.type === 'error') {
                            this.updateThreadCardError(threadCard, event.message);
                            // Mark thread as error
                            if (requestId && this.threads.has(requestId)) {
                                this.threads.get(requestId).status = 'error';
                            }
                            // Remove from in-flight tracking
                            if (requestId) {
                                this.inFlightRequests.delete(requestId);
                            }
                        }
                    } catch (e) {
                        // Ignore parse errors for incomplete JSON
                    }
                }
            }
        }

        // Finalize if stream ended without done event (fallback)
        if (threadCard.classList.contains('streaming')) {
            if (hasReceivedContent || toolCallsMade.length > 0) {
                if (!hasReceivedContent && toolCallsMade.length > 0) {
                    const displayTools = toolCallsMade.filter(t => t !== 'report_refs' && t !== 'send_message');
                    if (displayTools.length > 0) {
                        this.updateThreadCardResponse(threadCard, agentName, `✓ Completed: ${displayTools.join(', ')}`);
                    } else {
                        this.updateThreadCardResponse(threadCard, agentName, '✓ Done');
                    }
                }
                this.finalizeThreadCard(threadCard, agentId, agentName);
            } else {
                this.updateThreadCardError(threadCard, 'No response received from agent');
            }
        }

        // Clean up in-flight tracking
        if (requestId) {
            this.inFlightRequests.delete(requestId);
        }

        this.scrollToBottom();
    }

    addMessage(content, role, agentName = '', requestId = null) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;

        // Store request_id for threading
        if (requestId) {
            msgDiv.dataset.requestId = requestId;
        }

        if (role === 'assistant') {
            this.updateMessageContent(msgDiv, content, agentName);
        } else {
            msgDiv.textContent = content;
        }

        this.messagesContainer.appendChild(msgDiv);
        this.scrollToBottom();
        return msgDiv;
    }

    updateMessageContent(element, content, agentName) {
        let html = '';

        if (agentName) {
            html += `<div class="agent-name">${this.escapeHtml(agentName)}</div>`;
        }

        // Render markdown and auto-link URLs
        const renderedContent = this.renderMarkdown(content);
        html += `<div class="content">${renderedContent}</div>`;

        element.innerHTML = html;
        this.scrollToBottom();
    }

    renderMarkdown(text) {
        if (!text) return '';

        // Use marked.js if available
        if (typeof marked !== 'undefined') {
            try {
                console.log('marked object:', marked);
                console.log('marked.parse:', typeof marked.parse);
                console.log('Input text sample:', text.substring(0, 200));

                let html;
                if (typeof marked.parse === 'function') {
                    html = marked.parse(text);
                } else if (typeof marked === 'function') {
                    html = marked(text);
                } else {
                    console.error('marked.js loaded but no parse function found');
                    throw new Error('No parse function');
                }

                console.log('Output HTML sample:', html.substring(0, 200));

                // Make all links open in new tab
                html = html.replace(/<a href="/g, '<a target="_blank" rel="noopener noreferrer" href="');
                return html;
            } catch (e) {
                console.error('Marked.js error:', e);
            }
        } else {
            console.warn('marked.js not loaded, using fallback');
        }

        // Fallback: basic formatting
        let html = this.escapeHtml(text);

        // Auto-link URLs
        html = html.replace(
            /(https?:\/\/[^\s<]+)/g,
            '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
        );

        // Basic markdown
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        html = html.replace(/`(.+?)`/g, '<code>$1</code>');
        html = html.replace(/\n/g, '<br>');

        return html;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    scrollToBottom() {
        const container = this.messagesContainer.parentElement;
        container.scrollTop = container.scrollHeight;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.chatUI = new ChatUI();
});
