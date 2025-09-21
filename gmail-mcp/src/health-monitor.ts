/**
 * Enhanced Health Monitoring for Gmail MCP Server
 * Provides comprehensive health checks and monitoring capabilities
 */

import { OAuth2Client } from "google-auth-library";
import { google } from "googleapis";
import fs from "fs";
import path from "path";

export interface HealthStatus {
    status: "healthy" | "degraded" | "unhealthy";
    timestamp: string;
    service: string;
    version: string;
    uptime: number;
    dependencies: {
        gmail_api: "healthy" | "degraded" | "unhealthy";
        oauth_tokens: "healthy" | "degraded" | "unhealthy";
        external_apis: "healthy" | "degraded" | "unhealthy";
        file_system: "healthy" | "degraded" | "unhealthy";
    };
    metrics: {
        token_expiry_minutes?: number;
        last_token_refresh?: string;
        api_response_time_ms?: number;
        error_count_last_hour: number;
        request_count_last_hour: number;
    };
    errors?: string[];
}

export class GmailHealthMonitor {
    private oauth2Client: OAuth2Client | null = null;
    private gmail: any = null;
    private errorCount = 0;
    private requestCount = 0;
    private lastTokenRefresh: Date | null = null;
    private errorHistory: { timestamp: Date; error: string }[] = [];

    constructor() {
        // Clean up old error history (keep last hour)
        this.cleanupErrorHistory();
    }

    /**
     * Initialize the health monitor with OAuth client
     */
    async initialize(oauth2Client: OAuth2Client, gmail: any) {
        this.oauth2Client = oauth2Client;
        this.gmail = gmail;
        
        // Listen for token refresh events
        this.oauth2Client.on('tokens', (tokens) => {
            this.lastTokenRefresh = new Date();
            this.logError(`Token refreshed at ${this.lastTokenRefresh.toISOString()}`);
        });
    }

    /**
     * Perform comprehensive health check
     */
    async performHealthCheck(): Promise<HealthStatus> {
        const startTime = Date.now();
        const errors: string[] = [];
        let overallStatus: "healthy" | "degraded" | "unhealthy" = "healthy";

        // Check Gmail API connectivity
        const gmailApiStatus = await this.checkGmailApi();
        if (gmailApiStatus !== "healthy") {
            errors.push(`Gmail API: ${gmailApiStatus}`);
            if (gmailApiStatus === "unhealthy") overallStatus = "unhealthy";
            else if (overallStatus === "healthy") overallStatus = "degraded";
        }

        // Check OAuth tokens
        const oauthStatus = await this.checkOAuthTokens();
        if (oauthStatus !== "healthy") {
            errors.push(`OAuth tokens: ${oauthStatus}`);
            if (oauthStatus === "unhealthy") overallStatus = "unhealthy";
            else if (overallStatus === "healthy") overallStatus = "degraded";
        }

        // Check external APIs
        const externalApiStatus = await this.checkExternalApis();
        if (externalApiStatus !== "healthy") {
            errors.push(`External APIs: ${externalApiStatus}`);
            if (externalApiStatus === "unhealthy") overallStatus = "unhealthy";
            else if (overallStatus === "healthy") overallStatus = "degraded";
        }

        // Check file system
        const fileSystemStatus = await this.checkFileSystem();
        if (fileSystemStatus !== "healthy") {
            errors.push(`File system: ${fileSystemStatus}`);
            if (fileSystemStatus === "unhealthy") overallStatus = "unhealthy";
            else if (overallStatus === "healthy") overallStatus = "degraded";
        }

        const responseTime = Date.now() - startTime;

        // Calculate metrics
        const tokenExpiryMinutes = await this.getTokenExpiryMinutes();
        const errorsLastHour = this.getErrorCountLastHour();
        const requestsLastHour = this.getRequestCountLastHour();

        return {
            status: overallStatus,
            timestamp: new Date().toISOString(),
            service: "gmail-tools",
            version: process.env.MCP_SERVER_VERSION || "1.1.11",
            uptime: process.uptime(),
            dependencies: {
                gmail_api: gmailApiStatus,
                oauth_tokens: oauthStatus,
                external_apis: externalApiStatus,
                file_system: fileSystemStatus
            },
            metrics: {
                token_expiry_minutes: tokenExpiryMinutes,
                last_token_refresh: this.lastTokenRefresh?.toISOString(),
                api_response_time_ms: responseTime,
                error_count_last_hour: errorsLastHour,
                request_count_last_hour: requestsLastHour
            },
            errors: errors.length > 0 ? errors : undefined
        };
    }

    /**
     * Check Gmail API connectivity
     */
    private async checkGmailApi(): Promise<"healthy" | "degraded" | "unhealthy"> {
        if (!this.gmail) return "unhealthy";

        try {
            // Simple API call to test connectivity
            const response = await this.gmail.users.getProfile({
                userId: 'me'
            });
            
            if (response.data && response.data.emailAddress) {
                this.requestCount++;
                return "healthy";
            } else {
                this.logError("Gmail API returned invalid response");
                return "degraded";
            }
        } catch (error: any) {
            this.logError(`Gmail API error: ${error.message}`);
            this.errorCount++;
            
            // Check for specific error types
            if (error.code === 401 || error.code === 403) {
                return "unhealthy"; // Authentication/authorization issues
            } else if (error.code === 429) {
                return "degraded"; // Rate limiting
            } else {
                return "unhealthy"; // Other errors
            }
        }
    }

    /**
     * Check OAuth token status
     */
    private async checkOAuthTokens(): Promise<"healthy" | "degraded" | "unhealthy"> {
        if (!this.oauth2Client) return "unhealthy";

        try {
            const credentials = this.oauth2Client.credentials;
            
            if (!credentials.access_token) {
                this.logError("No access token available");
                return "unhealthy";
            }

            if (!credentials.refresh_token) {
                this.logError("No refresh token available");
                return "degraded";
            }

            // Check token expiry
            const expiryMinutes = await this.getTokenExpiryMinutes();
            if (expiryMinutes === null) {
                this.logError("Unable to determine token expiry");
                return "degraded";
            }

            if (expiryMinutes < 0) {
                this.logError("Access token has expired");
                return "unhealthy";
            } else if (expiryMinutes < 5) {
                this.logError("Access token expires soon");
                return "degraded";
            }

            return "healthy";
        } catch (error: any) {
            this.logError(`OAuth token check error: ${error.message}`);
            this.errorCount++;
            return "unhealthy";
        }
    }

    /**
     * Check external API dependencies
     */
    private async checkExternalApis(): Promise<"healthy" | "degraded" | "unhealthy"> {
        try {
            // Test Google OAuth endpoint
            const response = await fetch('https://oauth2.googleapis.com/token', {
                method: 'HEAD',
                timeout: 5000
            });
            
            if (response.ok) {
                return "healthy";
            } else {
                this.logError(`Google OAuth endpoint returned ${response.status}`);
                return "degraded";
            }
        } catch (error: any) {
            this.logError(`External API check error: ${error.message}`);
            this.errorCount++;
            return "unhealthy";
        }
    }

    /**
     * Check file system accessibility
     */
    private async checkFileSystem(): Promise<"healthy" | "degraded" | "unhealthy"> {
        try {
            const credentialsPath = process.env.GMAIL_CREDENTIALS_PATH || "/app/data/credentials.json";
            const oauthPath = process.env.GMAIL_OAUTH_PATH || "/app/config/gcp-oauth.keys.json";

            // Check if credential files are accessible
            const credentialsExists = fs.existsSync(credentialsPath);
            const oauthExists = fs.existsSync(oauthPath);

            if (!oauthExists) {
                this.logError("OAuth keys file not accessible");
                return "unhealthy";
            }

            if (!credentialsExists) {
                this.logError("Credentials file not accessible");
                return "degraded";
            }

            // Check file permissions
            try {
                fs.accessSync(credentialsPath, fs.constants.R_OK);
                fs.accessSync(oauthPath, fs.constants.R_OK);
            } catch (error: any) {
                this.logError(`File permission error: ${error.message}`);
                return "degraded";
            }

            return "healthy";
        } catch (error: any) {
            this.logError(`File system check error: ${error.message}`);
            this.errorCount++;
            return "unhealthy";
        }
    }

    /**
     * Get token expiry in minutes
     */
    private async getTokenExpiryMinutes(): Promise<number | null> {
        if (!this.oauth2Client) return null;

        try {
            const credentials = this.oauth2Client.credentials;
            if (!credentials.expiry_date) return null;

            const expiryTime = new Date(credentials.expiry_date);
            const currentTime = new Date();
            const diffMs = expiryTime.getTime() - currentTime.getTime();
            
            return Math.floor(diffMs / (1000 * 60));
        } catch (error: any) {
            this.logError(`Token expiry check error: ${error.message}`);
            return null;
        }
    }

    /**
     * Log error with timestamp
     */
    private logError(message: string) {
        this.errorHistory.push({
            timestamp: new Date(),
            error: message
        });
        this.cleanupErrorHistory();
    }

    /**
     * Clean up old error history (keep last hour)
     */
    private cleanupErrorHistory() {
        const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
        this.errorHistory = this.errorHistory.filter(entry => entry.timestamp > oneHourAgo);
    }

    /**
     * Get error count from last hour
     */
    private getErrorCountLastHour(): number {
        return this.errorHistory.length;
    }

    /**
     * Get request count from last hour (simplified)
     */
    private getRequestCountLastHour(): number {
        // In a real implementation, this would track requests over time
        // For now, return the total request count
        return this.requestCount;
    }

    /**
     * Get detailed health metrics
     */
    async getDetailedMetrics() {
        return {
            token_status: await this.checkOAuthTokens(),
            api_status: await this.checkGmailApi(),
            file_system_status: await this.checkFileSystem(),
            external_api_status: await this.checkExternalApis(),
            token_expiry_minutes: await this.getTokenExpiryMinutes(),
            error_count_last_hour: this.getErrorCountLastHour(),
            request_count_last_hour: this.getRequestCountLastHour(),
            uptime_seconds: process.uptime(),
            memory_usage: process.memoryUsage(),
            last_token_refresh: this.lastTokenRefresh
        };
    }
}
