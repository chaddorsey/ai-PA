# PBI-20: Dedicated Slack Analytics Export Service

[View in Backlog](../backlog.md#user-content-20)

## Overview
Provide a dedicated Slack analytics export microservice so Letta tools can trigger Slack workspace analytics reliably without depending on the Calendly MCP server runtime.

## Problem Statement
Slack analytics export functionality is currently embedded within the Calendly MCP server container, which does not expose the HTTP endpoint assumed by the Letta tool. The shared container creates operational coupling, inconsistent port exposure, and results in `Connection refused` errors when the export tool runs because the endpoint process is not actually started.

## User Stories
- As an integration engineer, I want Slack analytics exports exposed via a dedicated MCP-compatible service so that operational boundaries are clear and Letta can invoke exports without cross-service side effects.
- As an operations engineer, I want a health-checked Docker service that reliably handles Slack exports so that the deployment stack surfaces clear diagnostics when exports fail.

## Technical Approach
- Create a new `slack-analytics-mcp-server` service directory with FastAPI app based on the existing `slack_analytics_endpoint.py`, structured as a stand-alone container.
- Provide Dockerfile and Playwright/selenium dependencies as required for Slack automation, reusing patterns from `calendly-mcp-server` where appropriate.
- Expose service on internal hostname `slack-analytics-mcp-server` port `8087`, add to `pa-internal` network, and register health check.
- Update Letta tool registration (`trigger_slack_analytics_export`) to call the new service hostname and ensure configuration references environment variables or constants for host/port.
- Supply deployment and troubleshooting instructions in docs so operators understand prerequisites (Slack auth state, export scripts, service logs).

## UX/UI Considerations
No direct UI changes. Ensure Letta tool responses include actionable messaging for operators, and document any error outputs surfaced to end users in Letta conversations.

## Acceptance Criteria
- Docker Compose includes a `slack-analytics-mcp-server` service with independent lifecycle management.
- Service exposes `/health` and `/trigger-export` endpoints on port `8087` and passes health check within Compose environment.
- Letta tool `trigger_slack_analytics_export` succeeds in triggering exports using the new service when Slack credentials are configured, with no `Connection refused` errors under normal operation.
- Operational runbook details dependencies (auth files, scripts, environment variables) and troubleshooting steps.

## Dependencies
- Slack authentication artifacts (`slack_auth_state.json`, export automation scripts) must be accessible to the new service container.
- Docker environment must support Chromium/Playwright dependencies required by the export script.
- Letta environment must be able to reach the service via the `pa-internal` network.

## Open Questions
- Should the export script run with Playwright or Selenium, and are there licensing/maintenance considerations for bundling it?
- Do we need configurable rate limiting or concurrency controls for multiple export requests?
- Will the service share storage volumes with existing scripts, or should artifacts be baked into the image?

## Related Tasks
- [Tasks for PBI 20](./tasks.md)
