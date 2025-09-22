/**
 * Health monitoring types and interfaces
 */

export interface HealthStatus {
  status: 'healthy' | 'unhealthy' | 'degraded' | 'unknown';
  timestamp: string;
  service: string;
  version: string;
  uptime: number;
  dependencies: Record<string, string>;
  error?: string;
  responseTime?: number;
}

export interface MCPHealthCheck {
  service: string;
  url: string;
  port: number;
  path: string;
  timeout: number;
  retries: number;
  interval: number;
}

export interface HealthAggregation {
  overall: 'healthy' | 'unhealthy' | 'degraded';
  services: Record<string, HealthStatus>;
  timestamp: string;
  totalServices: number;
  healthyServices: number;
  unhealthyServices: number;
  degradedServices: number;
}

export interface HealthAlert {
  id: string;
  service: string;
  type: 'failure' | 'recovery' | 'degradation';
  message: string;
  timestamp: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  resolved: boolean;
}

export interface HealthMetrics {
  service: string;
  timestamp: string;
  responseTime: number;
  status: string;
  errorRate: number;
  uptime: number;
}

export interface HealthConfig {
  mcpServers: MCPHealthCheck[];
  aggregationInterval: number;
  alertThresholds: {
    responseTime: number;
    errorRate: number;
    consecutiveFailures: number;
  };
  notificationChannels: string[];
}

