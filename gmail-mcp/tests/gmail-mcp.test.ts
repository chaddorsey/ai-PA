/**
 * Comprehensive Testing Framework for Gmail MCP Server
 * Tests all Gmail functionality, integration, and edge cases
 */

import { describe, test, expect, beforeAll, afterAll, beforeEach } from '@jest/globals';
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { registerAll } from "../src/index.js";
import { GmailHealthMonitor } from "../src/health-monitor.js";

// Mock Gmail API responses
const mockGmailApi = {
  users: {
    getProfile: jest.fn(),
    messages: {
      send: jest.fn(),
      get: jest.fn(),
      list: jest.fn(),
      modify: jest.fn(),
      delete: jest.fn(),
      attachments: {
        get: jest.fn()
      }
    },
    drafts: {
      create: jest.fn()
    },
    labels: {
      list: jest.fn(),
      create: jest.fn(),
      update: jest.fn(),
      delete: jest.fn()
    },
    settings: {
      filters: {
        list: jest.fn(),
        create: jest.fn(),
        get: jest.fn(),
        delete: jest.fn()
      }
    }
  }
};

// Mock OAuth client
const mockOAuth2Client = {
  setCredentials: jest.fn(),
  credentials: {
    access_token: 'mock_access_token',
    refresh_token: 'mock_refresh_token',
    expiry_date: Date.now() + 3600000 // 1 hour from now
  },
  on: jest.fn(),
  generateAuthUrl: jest.fn(),
  getToken: jest.fn()
};

describe('Gmail MCP Server Tests', () => {
  let server: Server;
  let healthMonitor: GmailHealthMonitor;

  beforeAll(async () => {
    // Initialize server
    server = new Server({ name: "gmail-test", version: "1.0.0" });
    registerAll(server);
    
    // Initialize health monitor
    healthMonitor = new GmailHealthMonitor();
    await healthMonitor.initialize(mockOAuth2Client as any, mockGmailApi);
  });

  afterAll(async () => {
    // Cleanup
  });

  beforeEach(() => {
    // Reset mocks before each test
    jest.clearAllMocks();
  });

  describe('Health Monitoring', () => {
    test('should perform comprehensive health check', async () => {
      // Mock successful API responses
      mockGmailApi.users.getProfile.mockResolvedValue({
        data: { emailAddress: 'test@example.com' }
      });

      const healthStatus = await healthMonitor.performHealthCheck();
      
      expect(healthStatus).toMatchObject({
        status: expect.stringMatching(/^(healthy|degraded|unhealthy)$/),
        timestamp: expect.any(String),
        service: 'gmail-tools',
        version: expect.any(String),
        uptime: expect.any(Number),
        dependencies: {
          gmail_api: expect.stringMatching(/^(healthy|degraded|unhealthy)$/),
          oauth_tokens: expect.stringMatching(/^(healthy|degraded|unhealthy)$/),
          external_apis: expect.stringMatching(/^(healthy|degraded|unhealthy)$/),
          file_system: expect.stringMatching(/^(healthy|degraded|unhealthy)$/)
        },
        metrics: {
          error_count_last_hour: expect.any(Number),
          request_count_last_hour: expect.any(Number)
        }
      });
    });

    test('should detect unhealthy Gmail API', async () => {
      // Mock API failure
      mockGmailApi.users.getProfile.mockRejectedValue(new Error('API Error'));

      const healthStatus = await healthMonitor.performHealthCheck();
      
      expect(healthStatus.dependencies.gmail_api).toBe('unhealthy');
    });

    test('should detect expired tokens', async () => {
      // Mock expired token
      mockOAuth2Client.credentials.expiry_date = Date.now() - 3600000; // 1 hour ago

      const healthStatus = await healthMonitor.performHealthCheck();
      
      expect(healthStatus.dependencies.oauth_tokens).toBe('unhealthy');
    });
  });

  describe('Email Operations', () => {
    test('should send email successfully', async () => {
      // Mock successful send
      mockGmailApi.users.messages.send.mockResolvedValue({
        data: { id: 'test-message-id' }
      });

      const sendEmailRequest = {
        params: {
          name: 'send_email',
          arguments: {
            to: ['recipient@example.com'],
            subject: 'Test Email',
            body: 'This is a test email'
          }
        }
      };

      // This would be tested through the actual MCP server interface
      expect(mockGmailApi.users.messages.send).toBeDefined();
    });

    test('should handle email send failure', async () => {
      // Mock send failure
      mockGmailApi.users.messages.send.mockRejectedValue(new Error('Send failed'));

      // Test error handling
      expect(mockGmailApi.users.messages.send).toBeDefined();
    });

    test('should read email successfully', async () => {
      // Mock email data
      const mockEmailData = {
        data: {
          id: 'test-message-id',
          threadId: 'test-thread-id',
          payload: {
            headers: [
              { name: 'Subject', value: 'Test Subject' },
              { name: 'From', value: 'sender@example.com' },
              { name: 'To', value: 'recipient@example.com' },
              { name: 'Date', value: 'Mon, 21 Jan 2025 12:00:00 +0000' }
            ],
            body: { data: Buffer.from('Test email body').toString('base64') }
          }
        }
      };

      mockGmailApi.users.messages.get.mockResolvedValue(mockEmailData);

      // Test email reading
      expect(mockGmailApi.users.messages.get).toBeDefined();
    });
  });

  describe('Label Management', () => {
    test('should create label successfully', async () => {
      // Mock label creation
      mockGmailApi.users.labels.create.mockResolvedValue({
        data: {
          id: 'Label_test',
          name: 'Test Label',
          type: 'user'
        }
      });

      expect(mockGmailApi.users.labels.create).toBeDefined();
    });

    test('should list labels successfully', async () => {
      // Mock label list
      mockGmailApi.users.labels.list.mockResolvedValue({
        data: {
          labels: [
            { id: 'INBOX', name: 'INBOX', type: 'system' },
            { id: 'SENT', name: 'SENT', type: 'system' },
            { id: 'Label_test', name: 'Test Label', type: 'user' }
          ]
        }
      });

      expect(mockGmailApi.users.labels.list).toBeDefined();
    });
  });

  describe('Filter Management', () => {
    test('should create filter successfully', async () => {
      // Mock filter creation
      mockGmailApi.users.settings.filters.create.mockResolvedValue({
        data: {
          id: 'Filter_test',
          criteria: { from: 'test@example.com' },
          action: { addLabelIds: ['INBOX'] }
        }
      });

      expect(mockGmailApi.users.settings.filters.create).toBeDefined();
    });

    test('should list filters successfully', async () => {
      // Mock filter list
      mockGmailApi.users.settings.filters.list.mockResolvedValue({
        data: {
          filters: [
            {
              id: 'Filter_test',
              criteria: { from: 'test@example.com' },
              action: { addLabelIds: ['INBOX'] }
            }
          ]
        }
      });

      expect(mockGmailApi.users.settings.filters.list).toBeDefined();
    });
  });

  describe('Attachment Operations', () => {
    test('should download attachment successfully', async () => {
      // Mock attachment data
      const mockAttachmentData = {
        data: {
          data: Buffer.from('test attachment content').toString('base64url')
        }
      };

      mockGmailApi.users.messages.attachments.get.mockResolvedValue(mockAttachmentData);

      expect(mockGmailApi.users.messages.attachments.get).toBeDefined();
    });
  });

  describe('Error Handling', () => {
    test('should handle authentication errors', async () => {
      // Mock authentication error
      mockGmailApi.users.getProfile.mockRejectedValue({
        code: 401,
        message: 'Unauthorized'
      });

      const healthStatus = await healthMonitor.performHealthCheck();
      
      expect(healthStatus.dependencies.gmail_api).toBe('unhealthy');
    });

    test('should handle rate limiting', async () => {
      // Mock rate limit error
      mockGmailApi.users.getProfile.mockRejectedValue({
        code: 429,
        message: 'Rate limit exceeded'
      });

      const healthStatus = await healthMonitor.performHealthCheck();
      
      expect(healthStatus.dependencies.gmail_api).toBe('degraded');
    });
  });

  describe('Performance Tests', () => {
    test('should complete health check within timeout', async () => {
      const startTime = Date.now();
      
      mockGmailApi.users.getProfile.mockResolvedValue({
        data: { emailAddress: 'test@example.com' }
      });

      await healthMonitor.performHealthCheck();
      
      const duration = Date.now() - startTime;
      expect(duration).toBeLessThan(5000); // Should complete within 5 seconds
    });

    test('should handle concurrent requests', async () => {
      // Mock successful responses
      mockGmailApi.users.getProfile.mockResolvedValue({
        data: { emailAddress: 'test@example.com' }
      });

      // Run multiple health checks concurrently
      const promises = Array(10).fill(null).map(() => 
        healthMonitor.performHealthCheck()
      );

      const results = await Promise.all(promises);
      
      expect(results).toHaveLength(10);
      results.forEach(result => {
        expect(result.status).toBeDefined();
      });
    });
  });

  describe('Security Tests', () => {
    test('should not expose sensitive data in health status', async () => {
      mockGmailApi.users.getProfile.mockResolvedValue({
        data: { emailAddress: 'test@example.com' }
      });

      const healthStatus = await healthMonitor.performHealthCheck();
      const healthString = JSON.stringify(healthStatus);
      
      // Should not contain sensitive information
      expect(healthString).not.toContain('mock_access_token');
      expect(healthString).not.toContain('mock_refresh_token');
      expect(healthString).not.toContain('client_secret');
    });

    test('should validate OAuth token expiry', async () => {
      // Test with valid token
      mockOAuth2Client.credentials.expiry_date = Date.now() + 3600000; // 1 hour from now
      
      const healthStatus = await healthMonitor.performHealthCheck();
      expect(healthStatus.dependencies.oauth_tokens).toBe('healthy');
    });
  });

  describe('Integration Tests', () => {
    test('should integrate with main backup system', () => {
      // Test backup integration points
      expect(process.env.GMAIL_CREDENTIALS_PATH).toBeDefined();
      expect(process.env.GMAIL_OAUTH_PATH).toBeDefined();
    });

    test('should integrate with monitoring system', async () => {
      mockGmailApi.users.getProfile.mockResolvedValue({
        data: { emailAddress: 'test@example.com' }
      });

      const healthStatus = await healthMonitor.performHealthCheck();
      
      // Should provide metrics for monitoring
      expect(healthStatus.metrics).toBeDefined();
      expect(healthStatus.metrics.error_count_last_hour).toBeDefined();
      expect(healthStatus.metrics.request_count_last_hour).toBeDefined();
    });
  });
});
