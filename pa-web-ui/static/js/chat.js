// PA Web UI - Chat functionality

class ChatUI {
    constructor() {
        this.messagesContainer = document.getElementById('messages');
        this.messageInput = document.getElementById('message-input');
        this.sendBtn = document.getElementById('send-btn');
        this.agentSelect = document.getElementById('agent-select');

        this.sessionId = this.generateSessionId();
        this.isStreaming = false;

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

        // Create assistant message placeholder
        const assistantMsg = this.addMessage('', 'assistant');

        try {
            await this.streamResponse(message, assistantMsg);
        } catch (error) {
            console.error('Stream error:', error);
            assistantMsg.textContent = 'Error: Failed to get response';
        } finally {
            this.isStreaming = false;
            this.sendBtn.disabled = false;
            this.messageInput.focus();
        }
    }

    async streamResponse(message, msgElement) {
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
                        } else if (event.type === 'text') {
                            content += event.content;
                            msgElement.innerHTML = this.formatMessage(content, agentName);
                        } else if (event.type === 'error') {
                            msgElement.textContent = `Error: ${event.message}`;
                        }
                    } catch (e) {
                        // Ignore parse errors for incomplete JSON
                    }
                }
            }
        }

        // Scroll to bottom
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    addMessage(content, role) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        msgDiv.textContent = content;
        this.messagesContainer.appendChild(msgDiv);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        return msgDiv;
    }

    formatMessage(content, agentName) {
        let html = '';
        if (agentName) {
            html += `<div class="agent-name">${agentName}</div>`;
        }
        html += content;
        return html;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.chatUI = new ChatUI();
});
