#!/usr/bin/env node
/**
 * Health Monitor Service - Main entry point
 * 
 * This service provides centralized health monitoring for all MCP servers
 * in the PA ecosystem, including real-time status, alerting, and metrics.
 */

import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import cron from 'node-cron';
import { WebSocketServer } from 'ws';
import { createServer } from 'http';
import { HealthAggregator } from './health-aggregator.js';
import { MCPHealthCheck, HealthConfig } from './types.js';

const app = express();
const server = createServer(app);
const wss = new WebSocketServer({ server });

const PORT = Number(process.env.PORT || 8083);
const HEALTH_CHECK_INTERVAL = Number(process.env.HEALTH_CHECK_INTERVAL || 30); // seconds

// MCP Server configurations
const MCP_SERVERS: MCPHealthCheck[] = [
  {
    service: 'gmail-mcp-server',
    url: 'http://gmail-mcp-server:8080',
    port: 8080,
    path: '/health',
    timeout: 5000,
    retries: 3,
    interval: 30,
  },
  {
    service: 'graphiti-mcp-server',
    url: 'http://graphiti-mcp-server:8082',
    port: 8082,
    path: '/health',
    timeout: 5000,
    retries: 3,
    interval: 30,
  },
  {
    service: 'rag-mcp-server',
    url: 'http://rag-mcp-server:8082',
    port: 8082,
    path: '/health',
    timeout: 5000,
    retries: 3,
    interval: 30,
  },
];

// Initialize health aggregator
const healthAggregator = new HealthAggregator(MCP_SERVERS);

// Middleware
app.use(helmet());
app.use(cors());
app.use(morgan('combined'));
app.use(express.json());

// WebSocket connections for real-time updates
const clients = new Set<any>();

wss.on('connection', (ws) => {
  clients.add(ws);
  console.log('New WebSocket client connected');
  
  ws.on('close', () => {
    clients.delete(ws);
    console.log('WebSocket client disconnected');
  });
});

// Broadcast health updates to all connected clients
function broadcastHealthUpdate(data: any) {
  const message = JSON.stringify(data);
  clients.forEach(client => {
    if (client.readyState === 1) { // WebSocket.OPEN
      client.send(message);
    }
  });
}

// Health check endpoints
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    service: 'health-monitor',
    version: '1.0.0',
    uptime: process.uptime(),
    dependencies: {
      mcp_servers: MCP_SERVERS.length,
      websocket_clients: clients.size,
    },
  });
});

// Get overall health status
app.get('/api/health/overall', async (req, res) => {
  try {
    const aggregation = await healthAggregator.checkAllServices();
    res.json(aggregation);
  } catch (error) {
    res.status(500).json({
      error: 'Failed to check health status',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

// Get health status for a specific service
app.get('/api/health/service/:serviceName', async (req, res) => {
  try {
    const { serviceName } = req.params;
    const config = healthAggregator.getServiceConfig(serviceName);
    
    if (!config) {
      return res.status(404).json({ error: 'Service not found' });
    }

    const aggregation = await healthAggregator.checkAllServices();
    const serviceHealth = aggregation.services[serviceName];
    
    if (!serviceHealth) {
      return res.status(404).json({ error: 'Service health not available' });
    }

    res.json(serviceHealth);
  } catch (error) {
    res.status(500).json({
      error: 'Failed to check service health',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

// Get health history for a service
app.get('/api/health/history/:serviceName', (req, res) => {
  try {
    const { serviceName } = req.params;
    const history = healthAggregator.getHealthHistory(serviceName);
    
    if (history.size === 0) {
      return res.status(404).json({ error: 'Service not found or no history available' });
    }

    res.json(Array.from(history.values())[0]);
  } catch (error) {
    res.status(500).json({
      error: 'Failed to get health history',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

// Get alerts
app.get('/api/alerts', (req, res) => {
  try {
    const { service, resolved } = req.query;
    const alerts = healthAggregator.getAlerts(
      service as string,
      resolved ? resolved === 'true' : undefined
    );
    res.json(alerts);
  } catch (error) {
    res.status(500).json({
      error: 'Failed to get alerts',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

// Resolve an alert
app.post('/api/alerts/:alertId/resolve', (req, res) => {
  try {
    const { alertId } = req.params;
    const resolved = healthAggregator.resolveAlert(alertId);
    
    if (resolved) {
      res.json({ message: 'Alert resolved successfully' });
    } else {
      res.status(404).json({ error: 'Alert not found' });
    }
  } catch (error) {
    res.status(500).json({
      error: 'Failed to resolve alert',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

// Get service configurations
app.get('/api/services', (req, res) => {
  try {
    const services = healthAggregator.getAllServiceConfigs();
    res.json(services);
  } catch (error) {
    res.status(500).json({
      error: 'Failed to get service configurations',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

// Dashboard endpoint
app.get('/dashboard', (req, res) => {
  res.send(`
    <!DOCTYPE html>
    <html>
    <head>
        <title>PA Ecosystem Health Monitor</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
            .service-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .status-healthy { border-left: 4px solid #27ae60; }
            .status-unhealthy { border-left: 4px solid #e74c3c; }
            .status-degraded { border-left: 4px solid #f39c12; }
            .status-unknown { border-left: 4px solid #95a5a6; }
            .status-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
            .healthy { background: #27ae60; }
            .unhealthy { background: #e74c3c; }
            .degraded { background: #f39c12; }
            .unknown { background: #95a5a6; }
            .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-top: 10px; }
            .metric { text-align: center; padding: 10px; background: #ecf0f1; border-radius: 4px; }
            .refresh-btn { background: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin-bottom: 20px; }
            .refresh-btn:hover { background: #2980b9; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>PA Ecosystem Health Monitor</h1>
                <p>Real-time monitoring of MCP servers and system health</p>
            </div>
            
            <button class="refresh-btn" onclick="refreshData()">Refresh Data</button>
            
            <div id="overall-status"></div>
            <div id="services-grid" class="status-grid"></div>
        </div>

        <script>
            let ws;
            
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                ws = new WebSocket(protocol + '//' + window.location.host);
                
                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    updateDashboard(data);
                };
                
                ws.onclose = function() {
                    setTimeout(connectWebSocket, 5000);
                };
            }
            
            function refreshData() {
                fetch('/api/health/overall')
                    .then(response => response.json())
                    .then(data => updateDashboard(data))
                    .catch(error => console.error('Error fetching data:', error));
            }
            
            function updateDashboard(data) {
                updateOverallStatus(data);
                updateServicesGrid(data.services);
            }
            
            function updateOverallStatus(data) {
                const overallDiv = document.getElementById('overall-status');
                const statusClass = data.overall;
                const statusText = data.overall.charAt(0).toUpperCase() + data.overall.slice(1);
                
                overallDiv.innerHTML = \`
                    <div class="service-card status-\${statusClass}">
                        <h2>Overall Status: <span class="status-indicator \${statusClass}"></span>\${statusText}</h2>
                        <div class="metrics">
                            <div class="metric">
                                <strong>\${data.healthyServices}</strong><br>
                                Healthy
                            </div>
                            <div class="metric">
                                <strong>\${data.degradedServices}</strong><br>
                                Degraded
                            </div>
                            <div class="metric">
                                <strong>\${data.unhealthyServices}</strong><br>
                                Unhealthy
                            </div>
                            <div class="metric">
                                <strong>\${data.totalServices}</strong><br>
                                Total
                            </div>
                        </div>
                    </div>
                \`;
            }
            
            function updateServicesGrid(services) {
                const gridDiv = document.getElementById('services-grid');
                gridDiv.innerHTML = '';
                
                for (const [serviceName, serviceData] of Object.entries(services)) {
                    const serviceDiv = document.createElement('div');
                    serviceDiv.className = \`service-card status-\${serviceData.status}\`;
                    
                    const responseTime = serviceData.responseTime ? \`\${serviceData.responseTime}ms\` : 'N/A';
                    const uptime = serviceData.uptime ? \`\${Math.round(serviceData.uptime)}s\` : 'N/A';
                    
                    serviceDiv.innerHTML = \`
                        <h3>\${serviceName}</h3>
                        <p><strong>Status:</strong> <span class="status-indicator \${serviceData.status}"></span>\${serviceData.status}</p>
                        <p><strong>Version:</strong> \${serviceData.version}</p>
                        <p><strong>Response Time:</strong> \${responseTime}</p>
                        <p><strong>Uptime:</strong> \${uptime}</p>
                        \${serviceData.error ? \`<p><strong>Error:</strong> \${serviceData.error}</p>\` : ''}
                    \`;
                    
                    gridDiv.appendChild(serviceDiv);
                }
            }
            
            // Initialize
            connectWebSocket();
            refreshData();
            
            // Auto-refresh every 30 seconds
            setInterval(refreshData, 30000);
        </script>
    </body>
    </html>
  `);
});

// Scheduled health checks
cron.schedule(`*/${HEALTH_CHECK_INTERVAL} * * * * *`, async () => {
  try {
    console.log('Running scheduled health check...');
    const aggregation = await healthAggregator.checkAllServices();
    broadcastHealthUpdate(aggregation);
    console.log(`Health check completed. Overall status: ${aggregation.overall}`);
  } catch (error) {
    console.error('Scheduled health check failed:', error);
  }
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('Shutting down health monitor...');
  server.close(() => {
    process.exit(0);
  });
});

process.on('SIGTERM', () => {
  console.log('Shutting down health monitor...');
  server.close(() => {
    process.exit(0);
  });
});

// Start server
server.listen(PORT, () => {
  console.log(`Health Monitor service listening on port ${PORT}`);
  console.log(`Dashboard available at http://localhost:${PORT}/dashboard`);
  console.log(`Health API available at http://localhost:${PORT}/api/health`);
  console.log(`WebSocket available at ws://localhost:${PORT}`);
});

