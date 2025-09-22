/**
 * Health aggregation service for collecting and aggregating health status from all MCP servers
 */

import { HealthChecker } from './health-checker.js';
import { HealthStatus, HealthAggregation, MCPHealthCheck, HealthAlert } from './types.js';

export class HealthAggregator {
  private healthCheckers: Map<string, HealthChecker> = new Map();
  private healthHistory: Map<string, HealthStatus[]> = new Map();
  private alerts: HealthAlert[] = [];
  private config: MCPHealthCheck[];

  constructor(config: MCPHealthCheck[]) {
    this.config = config;
    this.initializeHealthCheckers();
  }

  private initializeHealthCheckers(): void {
    for (const serviceConfig of this.config) {
      const checker = new HealthChecker(serviceConfig);
      this.healthCheckers.set(serviceConfig.service, checker);
      this.healthHistory.set(serviceConfig.service, []);
    }
  }

  async checkAllServices(): Promise<HealthAggregation> {
    const serviceResults: Record<string, HealthStatus> = {};
    const promises: Promise<void>[] = [];

    // Check all services in parallel
    for (const [serviceName, checker] of this.healthCheckers) {
      const promise = checker.checkWithRetries().then(result => {
        serviceResults[serviceName] = result;
        this.updateHealthHistory(serviceName, result);
        this.checkForAlerts(serviceName, result);
      });
      promises.push(promise);
    }

    await Promise.all(promises);

    // Calculate overall health
    const overall = this.calculateOverallHealth(serviceResults);
    const counts = this.calculateHealthCounts(serviceResults);

    return {
      overall,
      services: serviceResults,
      timestamp: new Date().toISOString(),
      totalServices: this.config.length,
      healthyServices: counts.healthy,
      unhealthyServices: counts.unhealthy,
      degradedServices: counts.degraded,
    };
  }

  private updateHealthHistory(serviceName: string, healthStatus: HealthStatus): void {
    const history = this.healthHistory.get(serviceName) || [];
    history.push(healthStatus);
    
    // Keep only last 100 health checks per service
    if (history.length > 100) {
      history.shift();
    }
    
    this.healthHistory.set(serviceName, history);
  }

  private checkForAlerts(serviceName: string, healthStatus: HealthStatus): void {
    const history = this.healthHistory.get(serviceName) || [];
    const recentHistory = history.slice(-5); // Last 5 checks

    // Check for service failure
    if (healthStatus.status === 'unhealthy') {
      const recentFailures = recentHistory.filter(h => h.status === 'unhealthy').length;
      if (recentFailures >= 3) {
        this.createAlert(serviceName, 'failure', `Service ${serviceName} has been unhealthy for ${recentFailures} consecutive checks`, 'high');
      }
    }

    // Check for service recovery
    if (healthStatus.status === 'healthy' && history.length > 1) {
      const previousStatus = history[history.length - 2];
      if (previousStatus && previousStatus.status === 'unhealthy') {
        this.createAlert(serviceName, 'recovery', `Service ${serviceName} has recovered and is now healthy`, 'medium');
      }
    }

    // Check for performance degradation
    if (healthStatus.responseTime && healthStatus.responseTime > 5000) {
      this.createAlert(serviceName, 'degradation', `Service ${serviceName} response time is ${healthStatus.responseTime}ms`, 'medium');
    }
  }

  private createAlert(serviceName: string, type: 'failure' | 'recovery' | 'degradation', message: string, severity: 'low' | 'medium' | 'high' | 'critical'): void {
    const alert: HealthAlert = {
      id: `${serviceName}-${Date.now()}`,
      service: serviceName,
      type,
      message,
      timestamp: new Date().toISOString(),
      severity,
      resolved: false,
    };

    this.alerts.push(alert);
    
    // Keep only last 1000 alerts
    if (this.alerts.length > 1000) {
      this.alerts.shift();
    }
  }

  private calculateOverallHealth(services: Record<string, HealthStatus>): 'healthy' | 'unhealthy' | 'degraded' {
    const statuses = Object.values(services).map(s => s.status);
    
    if (statuses.some(s => s === 'unhealthy')) {
      return 'unhealthy';
    }
    
    if (statuses.some(s => s === 'degraded')) {
      return 'degraded';
    }
    
    return 'healthy';
  }

  private calculateHealthCounts(services: Record<string, HealthStatus>) {
    const counts = { healthy: 0, unhealthy: 0, degraded: 0 };
    
    for (const status of Object.values(services)) {
      switch (status.status) {
        case 'healthy':
          counts.healthy++;
          break;
        case 'unhealthy':
          counts.unhealthy++;
          break;
        case 'degraded':
          counts.degraded++;
          break;
      }
    }
    
    return counts;
  }

  getHealthHistory(serviceName?: string): Map<string, HealthStatus[]> {
    if (serviceName) {
      const history = this.healthHistory.get(serviceName);
      return history ? new Map([[serviceName, history]]) : new Map();
    }
    return new Map(this.healthHistory);
  }

  getAlerts(serviceName?: string, resolved?: boolean): HealthAlert[] {
    let filteredAlerts = this.alerts;
    
    if (serviceName) {
      filteredAlerts = filteredAlerts.filter(alert => alert.service === serviceName);
    }
    
    if (resolved !== undefined) {
      filteredAlerts = filteredAlerts.filter(alert => alert.resolved === resolved);
    }
    
    return filteredAlerts;
  }

  resolveAlert(alertId: string): boolean {
    const alert = this.alerts.find(a => a.id === alertId);
    if (alert) {
      alert.resolved = true;
      return true;
    }
    return false;
  }

  getServiceConfig(serviceName: string): MCPHealthCheck | undefined {
    return this.config.find(c => c.service === serviceName);
  }

  getAllServiceConfigs(): MCPHealthCheck[] {
    return [...this.config];
  }
}

