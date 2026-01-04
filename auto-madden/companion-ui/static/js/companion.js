/**
 * Auto-Madden Companion Client
 * 
 * Handles WebSocket connection, message display, and user interaction.
 */

class CompanionClient {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 3000;
        this.gameActive = false;
        this.statePollingInterval = null;
        this.liveMode = false;  // true when using live ESPN polling
        
        // DOM elements
        this.elements = {
            gameStatus: document.getElementById('game-status'),
            statusIndicator: document.querySelector('.status-indicator'),
            statusText: document.querySelector('.status-text'),
            gameInfo: document.getElementById('game-info'),
            startPanel: document.getElementById('start-panel'),
            chatContainer: document.getElementById('chat-container'),
            inputArea: document.getElementById('input-area'),
            messages: document.getElementById('messages'),
            teamInput: document.getElementById('team-input'),
            btnStart: document.getElementById('btn-start'),
            btnEnd: document.getElementById('btn-end'),
            messageInput: document.getElementById('message-input'),
            btnSend: document.getElementById('btn-send'),
            awayTeam: document.getElementById('away-team'),
            homeTeam: document.getElementById('home-team'),
            score: document.getElementById('score'),
            clock: document.getElementById('clock'),
            downDistance: document.getElementById('down-distance'),
            possession: document.getElementById('possession'),
            // Sync controls
            syncControls: document.getElementById('sync-controls'),
            delayDisplay: document.getElementById('delay-display'),
            btnDelayMinus: document.getElementById('btn-delay-minus'),
            btnDelayPlus: document.getElementById('btn-delay-plus'),
            btnSyncNow: document.getElementById('btn-sync-now')
        };
        
        // Track recent events for sync calibration
        this.recentEvents = [];
        this.currentDelay = 0;
        
        this.init();
    }
    
    init() {
        // Event listeners
        this.elements.btnStart.addEventListener('click', () => this.startSession());
        this.elements.teamInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.startSession();
        });
        
        this.elements.btnEnd.addEventListener('click', () => this.endSession());
        
        this.elements.btnSend.addEventListener('click', () => this.sendQuery());
        this.elements.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendQuery();
        });
        
        // Simulation mode
        const btnStartSim = document.getElementById('btn-start-sim');
        if (btnStartSim) {
            btnStartSim.addEventListener('click', () => this.startSimulation());
        }
        
        // Live mode
        const btnStartLive = document.getElementById('btn-start-live');
        if (btnStartLive) {
            btnStartLive.addEventListener('click', () => this.startLiveMode());
        }
        
        // Sync control buttons
        if (this.elements.btnDelayMinus) {
            this.elements.btnDelayMinus.addEventListener('click', () => this.adjustDelay(-5));
        }
        if (this.elements.btnDelayPlus) {
            this.elements.btnDelayPlus.addEventListener('click', () => this.adjustDelay(5));
        }
        if (this.elements.btnSyncNow) {
            this.elements.btnSyncNow.addEventListener('click', () => this.syncNow());
        }
        
        // Check for active simulation first, then load cached games
        this.checkActiveSimulation();
        
        // Connect WebSocket
        this.connect();
    }
    
    async checkActiveSimulation() {
        try {
            const response = await fetch('http://localhost:5132/state');
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'ok' && data.state) {
                    console.log('Found active simulation:', data.state.short_name);
                    this.connectToActiveSimulation(data.state);
                    return;
                }
            }
        } catch (e) {
            console.log('No active simulation found, showing game selection');
        }
        
        // No active simulation, load cached games for selection
        this.loadCachedGames();
        this.loadLiveGames();
    }
    
    connectToActiveSimulation(state) {
        // Show active simulation UI
        this.gameActive = true;
        this.elements.startPanel.style.display = 'none';
        this.elements.gameInfo.style.display = 'flex';
        this.elements.chatContainer.style.display = 'block';
        this.elements.inputArea.style.display = 'flex';
        this.elements.btnEnd.style.display = 'block';
        
        // Show sync controls
        if (this.elements.syncControls) {
            this.elements.syncControls.style.display = 'block';
        }
        
        // Update status indicator
        this.elements.statusIndicator.classList.add('connected');
        this.elements.statusText.textContent = 'Simulation Active';
        
        // Update display with current state
        this.updateGameStateDisplay(state);
        
        // Add system message
        this.addSystemMessage(`🎮 Connected to active simulation: ${state.short_name || state.game_name}`);
        this.addSystemMessage(`📺 Use the sync controls above to match your TV broadcast delay`);
        
        // Fetch current delay setting
        this.fetchDelayStatus();
        
        // Start polling for updates
        this.startStatePolling();
    }
    
    async fetchDelayStatus() {
        try {
            const response = await fetch('http://localhost:5131/delay');
            if (response.ok) {
                const data = await response.json();
                this.currentDelay = data.delay_seconds || 0;
                this.updateDelayDisplay();
            }
        } catch (e) {
            console.log('Could not fetch delay status:', e);
        }
    }
    
    async loadCachedGames() {
        const container = document.getElementById('cached-games');
        if (!container) {
            console.error('cached-games container not found');
            return;
        }
        
        container.innerHTML = '<p style="color: #8b949e;">Loading games...</p>';
        
        try {
            console.log('Fetching cached games from simulator...');
            const response = await fetch('http://localhost:5132/games');
            console.log('Response status:', response.status);
            
            if (response.ok) {
                const data = await response.json();
                console.log('Games data:', data);
                this.displayCachedGames(data.games || []);
            } else {
                container.innerHTML = '<p style="color: #f85149;">Failed to load games. Check simulator.</p>';
            }
        } catch (e) {
            console.error('Error loading cached games:', e);
            container.innerHTML = `
                <p style="color: #d29922; font-size: 13px;">⚠️ Simulator not responding</p>
                <p style="color: #8b949e; font-size: 12px;">Start it with: python3 game_simulator.py serve --port 5132</p>
            `;
        }
    }
    
    displayCachedGames(games) {
        const container = document.getElementById('cached-games');
        if (!container) return;
        
        if (games.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted);">No cached games available</p>';
            return;
        }
        
        console.log('Displaying cached games:', games);
        container.innerHTML = games.map((game, index) => `
            <label style="display: flex; align-items: center; padding: 12px 16px; margin: 8px 0; background: #21262d; border-radius: 8px; cursor: pointer; border: 2px solid #30363d; transition: border-color 0.2s;">
                <input type="radio" name="cached-game" value="${game.game_id}" ${index === 0 ? 'checked' : ''} style="width: 18px; height: 18px; margin-right: 12px; accent-color: #58a6ff;">
                <span style="font-weight: 600; color: #e6edf3;">${game.short_name}</span>
                <span style="color: #8b949e; font-size: 14px; margin-left: auto;">${game.home_team?.abbreviation || '?'} ${game.home_team?.score ?? 0} - ${game.away_team?.abbreviation || '?'} ${game.away_team?.score ?? 0}</span>
            </label>
        `).join('');
        
        // Select first by default
        const firstRadio = container.querySelector('input[type="radio"]');
        if (firstRadio) firstRadio.checked = true;
    }
    
    async startSimulation() {
        const selectedGame = document.querySelector('input[name="cached-game"]:checked');
        if (!selectedGame) {
            alert('Please select a game to simulate');
            return;
        }
        
        const gameId = selectedGame.value;
        const speed = parseFloat(document.getElementById('sim-speed').value) || 1.0;
        
        try {
            const response = await fetch('http://localhost:5132/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_id: gameId, speed: speed })
            });
            
            const result = await response.json();
            
            if (result.status === 'ok') {
                // Update UI
                this.gameActive = true;
                this.elements.startPanel.style.display = 'none';
                this.elements.gameInfo.style.display = 'flex';
                this.elements.chatContainer.style.display = 'block';
                this.elements.inputArea.style.display = 'flex';
                this.elements.btnEnd.style.display = 'block';
                
                if (result.game) {
                    this.updateGameInfo(result.game);
                }
                
                this.addSystemMessage(`🎮 Simulation started: ${result.message}`);
                this.addSystemMessage(`Playing at ${speed}x speed. Starting from play ${result.starting_play || 1} of ${result.total_plays}`);
                
                // Start polling for game state updates
                this.startStatePolling();
            } else {
                alert('Failed to start simulation: ' + result.message);
            }
        } catch (e) {
                alert('Error starting simulation: ' + e.message);
        }
    }
    
    async loadLiveGames() {
        const container = document.getElementById('live-games');
        if (!container) return;
        
        container.innerHTML = '<p style="color: #8b949e;">Loading live games...</p>';
        
        try {
            const response = await fetch('http://localhost:5132/live/espn/games');
            if (response.ok) {
                const data = await response.json();
                this.displayLiveGames(data.games || []);
            } else {
                container.innerHTML = '<p style="color: #8b949e;">No live games available</p>';
            }
        } catch (e) {
            container.innerHTML = '<p style="color: #8b949e;">Could not fetch live games</p>';
        }
    }
    
    displayLiveGames(games) {
        const container = document.getElementById('live-games');
        if (!container) return;
        
        if (games.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted);">No games available</p>';
            return;
        }
        
        container.innerHTML = games.map((game, index) => {
            const isLive = game.is_live;
            const liveIndicator = isLive ? '🔴' : '⏸️';
            const borderColor = isLive ? '#4CAF50' : '#30363d';
            
            return `
                <label style="display: flex; align-items: center; padding: 12px 16px; margin: 8px 0; background: #21262d; border-radius: 8px; cursor: pointer; border: 2px solid ${borderColor}; transition: border-color 0.2s;">
                    <input type="radio" name="live-game" value="${game.id}" ${index === 0 ? 'checked' : ''} style="width: 18px; height: 18px; margin-right: 12px; accent-color: #4CAF50;">
                    <span style="margin-right: 8px;">${liveIndicator}</span>
                    <span style="font-weight: 600; color: #e6edf3;">${game.away} @ ${game.home}</span>
                    <span style="color: #8b949e; font-size: 14px; margin-left: auto;">${game.status}</span>
                </label>
            `;
        }).join('');
    }
    
    async startLiveMode() {
        const selectedGame = document.querySelector('input[name="live-game"]:checked');
        if (!selectedGame) {
            alert('Please select a game');
            return;
        }
        
        const gameId = selectedGame.value;
        const pollInterval = parseInt(document.getElementById('poll-interval').value) || 15;
        
        try {
            const response = await fetch('http://localhost:5132/live/espn/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_id: gameId, interval: pollInterval })
            });
            
            const result = await response.json();
            
            if (result.status === 'ok') {
                // Mark as live mode
                this.liveMode = true;
                this.gameActive = true;
                
                // Update UI
                this.elements.startPanel.style.display = 'none';
                this.elements.gameInfo.style.display = 'flex';
                this.elements.chatContainer.style.display = 'block';
                this.elements.inputArea.style.display = 'flex';
                this.elements.btnEnd.style.display = 'block';
                
                // Show sync controls
                if (this.elements.syncControls) {
                    this.elements.syncControls.style.display = 'block';
                }
                
                // Update status
                this.elements.statusIndicator.classList.add('connected');
                this.elements.statusText.textContent = '📡 LIVE';
                
                this.addSystemMessage(`📡 Live mode started: ${result.message}`);
                this.addSystemMessage(`Polling ESPN every ${pollInterval} seconds`);
                
                // Fetch current delay
                this.fetchDelayStatus();
                
                // Start polling for updates (using live endpoint)
                this.startLiveStatePolling();
            } else {
                alert('Failed to start live mode: ' + result.message);
            }
        } catch (e) {
            alert('Error starting live mode: ' + e.message);
        }
    }
    
    startLiveStatePolling() {
        // Stop any existing polling
        this.stopStatePolling();
        
        // Poll every 2 seconds
        this.statePollingInterval = setInterval(() => this.pollLiveState(), 2000);
        
        // Also poll immediately
        this.pollLiveState();
    }
    
    async pollLiveState() {
        try {
            const response = await fetch('http://localhost:5132/live/espn/state');
            if (response.ok) {
                const data = await response.json();
                if (data.state) {
                    this.updateGameStateDisplay(data.state);
                }
            }
        } catch (e) {
            console.log('Error polling live state:', e);
        }
    }
    
    connect() {
        this.updateStatus('connecting', 'Connecting...');
        
        try {
            // Construct WebSocket URL
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = WS_URL || `${protocol}//${window.location.hostname}:5131/ws`;
            
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.reconnectAttempts = 0;
                this.updateStatus('connected', 'Connected');
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (e) {
                    console.error('Error parsing message:', e);
                }
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.updateStatus('disconnected', 'Disconnected');
                this.scheduleReconnect();
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
            
        } catch (e) {
            console.error('WebSocket connection failed:', e);
            this.scheduleReconnect();
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Reconnecting in ${this.reconnectDelay/1000}s (attempt ${this.reconnectAttempts})`);
            setTimeout(() => this.connect(), this.reconnectDelay);
        } else {
            this.updateStatus('disconnected', 'Connection failed');
        }
    }
    
    updateStatus(state, text) {
        this.elements.statusIndicator.className = 'status-indicator ' + state;
        this.elements.statusText.textContent = text;
    }
    
    handleMessage(data) {
        const type = data.type;
        
        switch (type) {
            case 'connected':
                console.log('Server acknowledged connection');
                break;
                
            case 'session_started':
                this.onSessionStarted(data.data);
                break;
                
            case 'session_ended':
                this.onSessionEnded();
                break;
                
            case 'insight':
                // Track event for sync calibration (especially score changes)
                if (data.data && data.data.type) {
                    this.recordEvent(data.data.type);
                }
                this.displayInsight(data.data);
                break;
                
            case 'game_state':
                this.updateGameState(data.data);
                break;
                
            case 'response':
                this.displayResponse(data.data);
                break;
                
            case 'error':
                this.displayError(data.message);
                break;
                
            default:
                console.log('Unknown message type:', type, data);
        }
    }
    
    startSession() {
        const team = this.elements.teamInput.value.trim();
        if (!team) {
            alert('Please enter a team name');
            return;
        }
        
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'start',
                query: team
            }));
            
            this.elements.btnStart.textContent = 'Starting...';
            this.elements.btnStart.disabled = true;
        } else {
            alert('Not connected to server. Please wait...');
        }
    }
    
    onSessionStarted(data) {
        this.gameActive = true;
        
        // Reset button
        this.elements.btnStart.textContent = 'Start Watching';
        this.elements.btnStart.disabled = false;
        
        // Update UI
        this.elements.startPanel.style.display = 'none';
        this.elements.gameInfo.style.display = 'flex';
        this.elements.chatContainer.style.display = 'block';
        this.elements.inputArea.style.display = 'flex';
        this.elements.btnEnd.style.display = 'block';
        
        // Update game info if available
        if (data.game) {
            this.updateGameInfo(data.game);
        }
        
        // Add welcome message
        this.addSystemMessage(`Now tracking: ${data.message || data.game?.short_name || 'Game'}`);
    }
    
    onSessionEnded() {
        this.gameActive = false;
        
        // Stop polling
        this.stopStatePolling();
        
        // Update UI
        this.elements.startPanel.style.display = 'flex';
        this.elements.gameInfo.style.display = 'none';
        this.elements.chatContainer.style.display = 'none';
        this.elements.inputArea.style.display = 'none';
        this.elements.btnEnd.style.display = 'none';
        
        // Hide sync controls
        if (this.elements.syncControls) {
            this.elements.syncControls.style.display = 'none';
        }
        
        // Clear messages and event history
        this.elements.messages.innerHTML = '';
        this.elements.teamInput.value = '';
        this.recentEvents = [];
    }
    
    async endSession() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'stop' }));
        }
        
        // Stop live mode if active
        if (this.liveMode) {
            try {
                await fetch('http://localhost:5132/live/espn/stop', { method: 'POST' });
            } catch (e) {
                console.log('Error stopping live mode:', e);
            }
            this.liveMode = false;
        }
        
        this.onSessionEnded();
    }
    
    sendQuery() {
        const text = this.elements.messageInput.value.trim();
        if (!text) return;
        
        // Display user message
        this.displayUserMessage(text);
        
        // Clear input
        this.elements.messageInput.value = '';
        
        // Show loading
        this.showLoading();
        
        // Send to server
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'query',
                text: text
            }));
        }
    }
    
    displayInsight(insight) {
        const typeClass = this.getInsightTypeClass(insight.type);
        const time = this.formatTime(insight.generated_at);
        
        const html = `
            <div class="message insight ${typeClass} new highlight">
                <div class="message-header">
                    <span class="message-time">${time}</span>
                    <span class="message-type">${this.formatType(insight.type)}</span>
                </div>
                <div class="message-headline">${insight.headline}</div>
                <div class="message-body">${insight.body}</div>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.scrollToBottom();
        
        // Remove highlight after animation
        setTimeout(() => {
            const newMessages = this.elements.messages.querySelectorAll('.new');
            newMessages.forEach(m => m.classList.remove('new', 'highlight'));
        }, 2000);
    }
    
    displayUserMessage(text) {
        const time = this.formatTime(new Date().toISOString());
        
        const html = `
            <div class="message user new">
                <div class="message-header">
                    <span class="message-time">${time}</span>
                    <span class="message-type">You</span>
                </div>
                <div class="message-body">${this.escapeHtml(text)}</div>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.scrollToBottom();
    }
    
    displayResponse(data) {
        this.hideLoading();
        
        const time = this.formatTime(new Date().toISOString());
        
        const html = `
            <div class="message response new">
                <div class="message-header">
                    <span class="message-time">${time}</span>
                    <span class="message-type">Auto-Madden</span>
                </div>
                <div class="message-body">${this.escapeHtml(data.answer)}</div>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.scrollToBottom();
    }
    
    displayError(message) {
        this.hideLoading();
        
        const html = `
            <div class="message response">
                <div class="message-body" style="color: var(--accent-red);">${this.escapeHtml(message)}</div>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.scrollToBottom();
    }
    
    addSystemMessage(text) {
        const html = `
            <div class="message" style="text-align: center; border-left: none;">
                <div class="message-body" style="color: var(--text-muted);">${this.escapeHtml(text)}</div>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.scrollToBottom();
    }
    
    showLoading() {
        const html = `
            <div class="loading" id="loading">
                <div class="loading-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
                <span>Thinking...</span>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.scrollToBottom();
    }
    
    hideLoading() {
        const loading = document.getElementById('loading');
        if (loading) loading.remove();
    }
    
    updateGameInfo(game) {
        if (game.short_name) {
            const parts = game.short_name.split(' @ ');
            if (parts.length === 2) {
                this.elements.awayTeam.textContent = parts[0];
                this.elements.homeTeam.textContent = parts[1];
            }
        }
        
        if (game.score) {
            this.elements.score.textContent = game.score;
        }
    }
    
    startStatePolling() {
        // Stop any existing polling
        this.stopStatePolling();
        
        // Poll every 2 seconds
        this.statePollingInterval = setInterval(() => this.pollGameState(), 2000);
        
        // Also poll immediately
        this.pollGameState();
    }
    
    stopStatePolling() {
        if (this.statePollingInterval) {
            clearInterval(this.statePollingInterval);
            this.statePollingInterval = null;
        }
    }
    
    async pollGameState() {
        try {
            const response = await fetch('http://localhost:5132/state');
            if (response.ok) {
                const data = await response.json();
                if (data.state) {
                    this.updateGameStateDisplay(data.state);
                }
            }
        } catch (e) {
            console.log('Error polling state:', e);
        }
    }
    
    updateGameStateDisplay(state) {
        // Update teams and score
        if (state.home_team && state.away_team) {
            this.elements.awayTeam.textContent = state.away_team.abbreviation || 'AWAY';
            this.elements.homeTeam.textContent = state.home_team.abbreviation || 'HOME';
            
            const homeScore = state.home_team.score ?? 0;
            const awayScore = state.away_team.score ?? 0;
            this.elements.score.textContent = `${awayScore} - ${homeScore}`;
        }
        
        // Update clock - this is the key part!
        const quarter = state.quarter || 1;
        const clock = state.clock || '15:00';
        this.elements.clock.textContent = `Q${quarter} · ${clock}`;
        
        // Update down and distance
        const down = state.down || 1;
        const distance = state.distance || 10;
        this.elements.downDistance.textContent = `${this.ordinal(down)} & ${distance}`;
        
        // Update possession
        if (state.possession_team) {
            this.elements.possession.textContent = state.possession_team;
        } else {
            this.elements.possession.textContent = '';
        }
    }
    
    updateGameState(state) {
        if (state.home_team && state.away_team) {
            this.elements.awayTeam.textContent = state.away_team.abbreviation;
            this.elements.homeTeam.textContent = state.home_team.abbreviation;
            this.elements.score.textContent = `${state.home_team.score} - ${state.away_team.score}`;
        }
        
        this.elements.clock.textContent = `Q${state.quarter} · ${state.clock}`;
        this.elements.downDistance.textContent = `${this.ordinal(state.down)} & ${state.distance}`;
        this.elements.possession.textContent = state.possession_team || '';
    }
    
    getInsightTypeClass(type) {
        const mapping = {
            'situation_explanation': 'situation',
            'play_explanation': 'play-explanation',
            'prediction': 'prediction',
            'turnover': 'turnover',
            'score_change': 'score',
            'red_zone_entry': 'situation',
            'two_minute_warning': 'situation',
            'momentum_shift': 'prediction'
        };
        return mapping[type] || '';
    }
    
    formatType(type) {
        const mapping = {
            'situation_explanation': 'Situation',
            'play_explanation': 'Play',
            'prediction': 'Watch For',
            'turnover': 'Turnover',
            'score_change': 'Score',
            'red_zone_entry': 'Red Zone',
            'two_minute_warning': 'Two Minute',
            'momentum_shift': 'Momentum',
            'llm_generated': 'Insight'
        };
        return mapping[type] || 'Update';
    }
    
    formatTime(isoString) {
        try {
            const date = new Date(isoString);
            return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        } catch (e) {
            return '';
        }
    }
    
    ordinal(n) {
        const s = ['th', 'st', 'nd', 'rd'];
        const v = n % 100;
        return n + (s[(v - 20) % 10] || s[v] || s[0]);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // ========== Broadcast Sync Controls ==========
    
    async adjustDelay(delta) {
        try {
            const response = await fetch('http://localhost:5131/delay/adjust', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ delta_seconds: delta })
            });
            
            if (response.ok) {
                const data = await response.json();
                this.currentDelay = data.delay_seconds;
                this.updateDelayDisplay();
                this.addSystemMessage(`📺 Delay adjusted to ${this.currentDelay.toFixed(1)}s`);
            }
        } catch (e) {
            console.log('Error adjusting delay:', e);
        }
    }
    
    async syncNow() {
        // Record that the user just saw a significant event on TV
        // This helps calibrate the delay
        const now = Date.now() / 1000;
        
        // Find the most recent event we received
        if (this.recentEvents.length > 0) {
            const lastEvent = this.recentEvents[this.recentEvents.length - 1];
            
            try {
                const response = await fetch('http://localhost:5131/delay/sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        event_type: lastEvent.type,
                        event_time: lastEvent.time
                    })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    this.currentDelay = data.delay_seconds;
                    this.updateDelayDisplay();
                    this.addSystemMessage(`🎯 Synced! Delay calibrated to ${this.currentDelay.toFixed(1)}s`);
                }
            } catch (e) {
                console.log('Error syncing:', e);
            }
        } else {
            this.addSystemMessage(`📺 Wait for a scoring play, then click "That Just Happened!" when you see it on TV`);
        }
    }
    
    updateDelayDisplay() {
        if (this.elements.delayDisplay) {
            this.elements.delayDisplay.textContent = `${this.currentDelay.toFixed(0)}s delay`;
        }
    }
    
    recordEvent(type) {
        // Track when we receive events for sync calibration
        this.recentEvents.push({
            type: type,
            time: Date.now() / 1000
        });
        // Keep last 10 events
        if (this.recentEvents.length > 10) {
            this.recentEvents.shift();
        }
    }
    
    scrollToBottom() {
        const container = this.elements.chatContainer;
        container.scrollTop = container.scrollHeight;
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.companion = new CompanionClient();
});

