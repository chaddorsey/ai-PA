// http-bridge.ts
import http from 'http';
import { spawn } from 'child_process';
class MCPHttpBridge {
    port;
    mcpProcess = null;
    requestId = 1;
    pendingRequests = new Map();
    buffer = '';
    constructor(port = 8888) {
        this.port = port;
    }
    startMCPServer() {
        console.log('Starting OmniFocus MCP server...');
        this.mcpProcess = spawn('node', ['dist/server.js'], {
            stdio: ['pipe', 'pipe', 'inherit'],
            cwd: process.cwd()
        });
        if (!this.mcpProcess.stdout || !this.mcpProcess.stdin) {
            throw new Error('Failed to create MCP process pipes');
        }
        this.mcpProcess.stdout.setEncoding('utf8');
        this.mcpProcess.stdout.on('data', (data) => {
            this.handleMCPOutput(data);
        });
        this.mcpProcess.on('spawn', () => {
            console.log('✅ MCP server process spawned successfully');
        });
        this.mcpProcess.on('error', (error) => {
            console.error('❌ MCP process error:', error);
            this.restartMCPServer();
        });
        this.mcpProcess.on('exit', (code, signal) => {
            console.log(`⚠️ MCP process exited with code ${code}${signal ? ` (signal: ${signal})` : ''}`);
            this.mcpProcess = null;
            // Clean up pending requests
            this.pendingRequests.forEach(({ res, timeout }) => {
                clearTimeout(timeout);
                if (!res.headersSent) {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({
                        jsonrpc: '2.0',
                        error: { code: -32603, message: 'MCP server disconnected' }
                    }));
                }
            });
            this.pendingRequests.clear();
            // Auto-restart if not manually killed
            if (code !== 0) {
                console.log('🔄 Auto-restarting MCP server...');
                setTimeout(() => {
                    this.startMCPServer();
                }, 2000);
            }
        });
        console.log('✅ MCP server started');
    }
    restartMCPServer() {
        if (this.mcpProcess) {
            this.mcpProcess.kill();
            this.mcpProcess = null;
        }
        setTimeout(() => {
            this.startMCPServer();
        }, 1000);
    }
    handleMCPOutput(data) {
        this.buffer += data;
        const lines = this.buffer.split('\n');
        this.buffer = lines.pop() || ''; // Keep incomplete line in buffer
        for (const line of lines) {
            const trimmedLine = line.trim();
            if (trimmedLine) {
                try {
                    const response = JSON.parse(trimmedLine);
                    this.handleMCPResponse(response);
                }
                catch (error) {
                    console.error('Failed to parse MCP response:', error);
                    console.error('Raw line:', trimmedLine);
                }
            }
        }
    }
    handleMCPResponse(response) {
        if (response.error) {
            console.error('❌ MCP Error:', JSON.stringify(response.error, null, 2));
        }
        if (response.id && this.pendingRequests.has(response.id)) {
            const { res, timeout } = this.pendingRequests.get(response.id);
            clearTimeout(timeout);
            this.pendingRequests.delete(response.id);
            if (!res.headersSent) {
                res.writeHead(200, {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                });
                res.end(JSON.stringify(response, null, 2));
            }
        }
        else {
            // Notification or response without matching request
            console.log('📨 Unmatched MCP response:', JSON.stringify(response, null, 2));
        }
    }
    sendToMCP(request, res) {
        if (!this.mcpProcess || !this.mcpProcess.stdin) {
            res.writeHead(503, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({
                jsonrpc: '2.0',
                error: { code: -32603, message: 'MCP server not available' }
            }));
            return;
        }
        // Assign ID if not present
        if (!request.id) {
            request.id = this.requestId++;
        }
        // Set up timeout
        const timeout = setTimeout(() => {
            if (this.pendingRequests.has(request.id)) {
                this.pendingRequests.delete(request.id);
                if (!res.headersSent) {
                    res.writeHead(504, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({
                        jsonrpc: '2.0',
                        id: request.id,
                        error: { code: -32603, message: 'Request timeout' }
                    }));
                }
            }
        }, 30000); // 30 second timeout
        // Store pending request
        this.pendingRequests.set(request.id, { res, timeout });
        // Send request to MCP server
        try {
            this.mcpProcess.stdin.write(JSON.stringify(request) + '\n');
        }
        catch (error) {
            clearTimeout(timeout);
            this.pendingRequests.delete(request.id);
            console.error('Failed to send request to MCP:', error);
            if (!res.headersSent) {
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({
                    jsonrpc: '2.0',
                    id: request.id,
                    error: { code: -32603, message: 'Failed to send request to MCP server' }
                }));
            }
        }
    }
    createServer() {
        return http.createServer((req, res) => {
            // Handle CORS preflight
            if (req.method === 'OPTIONS') {
                res.writeHead(200, {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                });
                res.end();
                return;
            }
            // Health check endpoint
            if (req.method === 'GET' && req.url === '/health') {
                const isHealthy = this.mcpProcess && !this.mcpProcess.killed;
                res.writeHead(isHealthy ? 200 : 503, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({
                    status: isHealthy ? 'healthy' : 'unhealthy',
                    mcpServerRunning: !!this.mcpProcess && !this.mcpProcess.killed,
                    pendingRequests: this.pendingRequests.size
                }));
                return;
            }
            // API info endpoint
            if (req.method === 'GET' && req.url === '/') {
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({
                    name: 'OmniFocus MCP HTTP Bridge',
                    version: '1.0.0',
                    endpoints: {
                        '/': 'API information',
                        '/health': 'Health check',
                        '/mcp': 'MCP JSON-RPC endpoint (POST)'
                    },
                    usage: 'POST JSON-RPC requests to /mcp',
                    example: {
                        method: 'POST',
                        url: '/mcp',
                        body: {
                            jsonrpc: '2.0',
                            method: 'tools/list',
                            id: 1
                        }
                    }
                }, null, 2));
                return;
            }
            // Main MCP endpoint
            if (req.method === 'POST' && (req.url === '/mcp' || req.url === '/')) {
                let body = '';
                req.on('data', (chunk) => {
                    body += chunk.toString();
                });
                req.on('end', () => {
                    try {
                        const jsonRequest = JSON.parse(body);
                        // Validate basic JSON-RPC structure
                        if (!jsonRequest.jsonrpc || !jsonRequest.method) {
                            res.writeHead(400, { 'Content-Type': 'application/json' });
                            res.end(JSON.stringify({
                                jsonrpc: '2.0',
                                error: {
                                    code: -32600,
                                    message: 'Invalid Request: missing jsonrpc or method'
                                }
                            }));
                            return;
                        }
                        this.sendToMCP(jsonRequest, res);
                    }
                    catch (error) {
                        res.writeHead(400, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({
                            jsonrpc: '2.0',
                            error: {
                                code: -32700,
                                message: 'Parse error: Invalid JSON'
                            }
                        }));
                    }
                });
                req.on('error', (error) => {
                    console.error('Request error:', error);
                    if (!res.headersSent) {
                        res.writeHead(500, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({
                            jsonrpc: '2.0',
                            error: { code: -32603, message: 'Internal error' }
                        }));
                    }
                });
                return;
            }
            // 404 for other paths
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({
                error: 'Not Found',
                availableEndpoints: ['/', '/health', '/mcp']
            }));
        });
    }
    start() {
        this.startMCPServer();
        const server = this.createServer();
        server.listen(this.port, '0.0.0.0', () => {
            console.log(`🚀 OmniFocus MCP HTTP Bridge listening on port ${this.port}`);
            console.log(`   Health check: http://localhost:${this.port}/health`);
            console.log(`   API endpoint: http://localhost:${this.port}/mcp`);
            // Start process health monitoring
            this.startHealthMonitoring();
        });
        // Graceful shutdown
        process.on('SIGINT', () => {
            console.log('\n📤 Shutting down HTTP bridge...');
            server.close(() => {
                if (this.mcpProcess) {
                    this.mcpProcess.kill();
                }
                process.exit(0);
            });
        });
        return server;
    }
    startHealthMonitoring() {
        // Check process health every 10 seconds
        setInterval(() => {
            if (this.mcpProcess && this.mcpProcess.killed) {
                console.log('⚠️ MCP process died, restarting...');
                this.restartMCPServer();
            }
        }, 10000);
    }
}
// CLI usage - ES module version
if (import.meta.url === `file://${process.argv[1]}`) {
    const port = parseInt(process.argv[2]) || 8888;
    const bridge = new MCPHttpBridge(port);
    bridge.start();
}
export { MCPHttpBridge };
