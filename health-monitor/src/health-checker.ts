/**
 * Health checker for MCP servers
 */

import axios, { AxiosResponse } from 'axios';
import { HealthStatus, MCPHealthCheck } from './types.js';

export class HealthChecker {
  private config: MCPHealthCheck;

  constructor(config: MCPHealthCheck) {
    this.config = config;
  }

  async checkHealth(): Promise<HealthStatus> {
    const startTime = Date.now();
    const baseUrl = `http://${this.config.service}:${this.config.port}`;
    const healthUrl = `${baseUrl}${this.config.path}`;

    try {
      const response: AxiosResponse = await axios.get(healthUrl, {
        timeout: this.config.timeout,
        validateStatus: (status) => status < 500, // Accept 4xx as valid responses
      });

      const responseTime = Date.now() - startTime;
      const healthData = response.data;

      // Parse health response
      const status = this.parseHealthResponse(healthData, response.status);
      
      return {
        ...status,
        responseTime,
        timestamp: new Date().toISOString(),
        service: this.config.service,
      };
    } catch (error) {
      const responseTime = Date.now() - startTime;
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      
      return {
        status: 'unhealthy',
        timestamp: new Date().toISOString(),
        service: this.config.service,
        version: 'unknown',
        uptime: 0,
        dependencies: {},
        error: errorMessage,
        responseTime,
      };
    }
  }

  private parseHealthResponse(data: any, statusCode: number): Omit<HealthStatus, 'responseTime' | 'timestamp' | 'service'> {
    // Handle different response formats
    if (typeof data === 'object' && data !== null) {
      return {
        status: statusCode === 200 ? 'healthy' : 'degraded',
        version: data.version || 'unknown',
        uptime: data.uptime || 0,
        dependencies: data.dependencies || {},
        error: statusCode !== 200 ? `HTTP ${statusCode}` : undefined,
      };
    }

    // Fallback for non-JSON responses
    return {
      status: statusCode === 200 ? 'healthy' : 'unhealthy',
      version: 'unknown',
      uptime: 0,
      dependencies: {},
      error: statusCode !== 200 ? `HTTP ${statusCode}` : undefined,
    };
  }

  async checkWithRetries(): Promise<HealthStatus> {
    let lastError: Error | null = null;
    
    for (let attempt = 1; attempt <= this.config.retries; attempt++) {
      try {
        const result = await this.checkHealth();
        if (result.status === 'healthy') {
          return result;
        }
        lastError = new Error(`Health check failed: ${result.error}`);
      } catch (error) {
        lastError = error instanceof Error ? error : new Error('Unknown error');
        if (attempt < this.config.retries) {
          // Wait before retry
          await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
        }
      }
    }

    // All retries failed
    return {
      status: 'unhealthy',
      timestamp: new Date().toISOString(),
      service: this.config.service,
      version: 'unknown',
      uptime: 0,
      dependencies: {},
      error: lastError?.message || 'All retries failed',
      responseTime: 0,
    };
  }
}
