// PA Web UI - Chat functionality with streaming feedback

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

        this.sessionId = this.generateSessionId();
        this.isStreaming = false;
        this.statusIndicator = null;

        // Configure marked for safe rendering
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,  // Convert \n to <br>
                gfm: true,     // GitHub Flavored Markdown
            });
        }

        this.setupEventListeners();
        this.loadAgents();
    }

    generateSessionId() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    setupEventListeners() {
        this.sendBtn.addEventListener('click', () => this.sendMessage());

        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Auto-resize textarea
        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 150) + 'px';
        });
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

    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isStreaming) return;

        // Add user message to UI
        this.addMessage(message, 'user');
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';

        // Disable input during streaming
        this.isStreaming = true;
        this.sendBtn.disabled = true;

        // Show status indicator
        this.showStatusIndicator('Connecting...');

        try {
            await this.streamResponse(message);
        } catch (error) {
            console.error('Stream error:', error);
            this.removeStatusIndicator();
            this.addMessage('Error: Failed to get response', 'assistant', 'Error');
        } finally {
            this.isStreaming = false;
            this.sendBtn.disabled = false;
            this.messageInput.focus();
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

    async streamResponse(message) {
        const response = await fetch('/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                agent_id: this.agentSelect.value || null,
                session_id: this.sessionId
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let content = '';
        let agentName = '';
        let msgElement = null;

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
                            this.updateStatusIndicator(`Connected to ${agentName}...`);
                        } else if (event.type === 'tool_call') {
                            // Show contextual status for tool calls
                            const toolName = event.tool || 'unknown';
                            const statusText = TOOL_STATUS_MAP[toolName] || `Running ${toolName}...`;
                            this.updateStatusIndicator(statusText);
                        } else if (event.type === 'text') {
                            // First text received - remove status, create message
                            if (!msgElement) {
                                this.removeStatusIndicator();
                                msgElement = this.addMessage('', 'assistant', agentName);
                            }
                            content += event.content;
                            this.updateMessageContent(msgElement, content, agentName);
                        } else if (event.type === 'token') {
                            // Token-by-token streaming
                            if (!msgElement) {
                                this.removeStatusIndicator();
                                msgElement = this.addMessage('', 'assistant', agentName);
                            }
                            content += event.token;
                            this.updateMessageContent(msgElement, content, agentName);
                        } else if (event.type === 'done') {
                            this.removeStatusIndicator();
                        } else if (event.type === 'error') {
                            this.removeStatusIndicator();
                            this.addMessage(`Error: ${event.message}`, 'assistant', 'Error');
                        }
                    } catch (e) {
                        // Ignore parse errors for incomplete JSON
                    }
                }
            }
        }

        // Ensure status is removed even if no done event
        this.removeStatusIndicator();
        this.scrollToBottom();
    }

    addMessage(content, role, agentName = '') {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;

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
            let html = marked.parse(text);
            // Make all links open in new tab
            html = html.replace(/<a href="/g, '<a target="_blank" rel="noopener noreferrer" href="');
            return html;
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
