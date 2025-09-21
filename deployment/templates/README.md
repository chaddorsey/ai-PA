# PA Ecosystem Environment Templates

This directory contains pre-configured environment templates for different deployment scenarios.

## Available Templates

### 1. Development Template (`development.env`)
**Best for**: Development and testing environments

**Features**:
- Minimal external dependencies
- Debug logging enabled
- Local access only
- Example API keys (replace with real ones)
- All features enabled for testing

**Use when**:
- Setting up a development environment
- Testing new features
- Learning the system
- Local development without external access

### 2. Production Template (`production.env`)
**Best for**: Production deployments

**Features**:
- Security-focused configuration
- Performance-optimized models
- External access ready
- All values must be replaced with real configuration
- Production-grade settings

**Use when**:
- Deploying to production
- Need external access
- Security is a priority
- Performance is important

### 3. Minimal Template (`minimal.env`)
**Best for**: Resource-constrained environments

**Features**:
- Only essential features enabled
- Lightweight models
- Local access only
- Minimal resource usage
- Disabled optional integrations

**Use when**:
- Limited system resources
- Basic functionality only
- Cost optimization
- Simple deployments

### 4. Cloudflare Template (`cloudflare.env`)
**Best for**: External access via Cloudflare tunnels

**Features**:
- Pre-configured for Cloudflare tunnels
- HTTPS configuration
- Domain-based access
- Production-ready with external access
- Cloudflare-specific settings

**Use when**:
- Need external access
- Using Cloudflare for tunneling
- Want domain-based access
- Production deployment with external access

### 5. Local-Only Template (`local-only.env`)
**Best for**: Local development with all features

**Features**:
- All features enabled locally
- Debug logging enabled
- Optional external integrations
- Local access URLs
- Full functionality for development

**Use when**:
- Local development with full features
- Testing all integrations locally
- Development without external access
- Learning all system capabilities

### 6. Custom Template (`custom.env`)
**Best for**: Maximum customization

**Features**:
- All configuration options available
- Detailed comments and explanations
- Manual configuration required
- Maximum flexibility
- All features configurable

**Use when**:
- Need specific configuration
- Advanced users
- Custom deployment requirements
- Want full control over settings

## Template Selection

### Automatic Selection
Use the template selection script to choose the appropriate template:

```bash
./deployment/scripts/select-template.sh
```

### Manual Selection
1. Copy the desired template to your project root:
   ```bash
   cp deployment/templates/development.env .env
   ```

2. Edit the `.env` file with your actual configuration values

3. Validate your configuration:
   ```bash
   ./deployment/scripts/validate-config.sh
   ```

## Configuration Guide

### Required Variables
All templates include these essential variables:
- `POSTGRES_PASSWORD` - Database password (minimum 32 characters)
- `SUPABASE_ANON_KEY` - Supabase anonymous key
- `SUPABASE_SERVICE_KEY` - Supabase service key
- `N8N_ENCRYPTION_KEY` - N8N encryption key (32+ characters)
- `OPENAI_API_KEY` - OpenAI API key

### API Keys
Replace placeholder values with your actual API keys:
- **OpenAI**: Get from [OpenAI Platform](https://platform.openai.com/api-keys)
- **Anthropic**: Get from [Anthropic Console](https://console.anthropic.com/settings/keys)
- **Google Gemini**: Get from [Google AI Studio](https://aistudio.google.com/app/apikey)
- **Tavily**: Get from [Tavily Dashboard](https://app.tavily.com/home)

### External Access
For external access, configure one of:
- **Cloudflare Tunnels**: Set `CLOUDFLARE_*` variables
- **Ngrok**: Set `NGROK_AUTHTOKEN` and optionally `NGROK_DOMAIN`

### Slack Integration
For Slack integration:
- Create a Slack app at [api.slack.com](https://api.slack.com/apps)
- Get bot token, app token, and user token
- Set `SLACK_*` variables and `LETTA_AGENT_ID`

### Gmail Integration
For Gmail MCP integration:
- Create Google OAuth credentials
- Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`

## Validation

After configuring your `.env` file, validate it:

```bash
./deployment/scripts/validate-config.sh
```

This will check:
- Required variables are set
- API key formats are valid
- Password strength is adequate
- URL formats are correct
- No placeholder values remain

## Security Notes

1. **Never commit `.env` files** to version control
2. **Use strong passwords** (minimum 32 characters)
3. **Generate secure encryption keys** using `openssl rand -base64 32`
4. **Rotate API keys** regularly
5. **Use environment-specific values** for different deployments

## Troubleshooting

### Common Issues

1. **"Required variable not set"**
   - Check that all required variables are defined
   - Ensure no typos in variable names

2. **"API key format invalid"**
   - Verify API key format matches expected pattern
   - Check for extra spaces or characters

3. **"Password too short"**
   - Use passwords with at least 32 characters
   - Generate secure passwords

4. **"Placeholder values found"**
   - Replace all `CHANGE_ME_*` values with real configuration
   - Use the validation script to identify remaining placeholders

### Getting Help

- Check the configuration reference: `docs/delivery/7/7-6.md`
- Review the troubleshooting guide: `docs/delivery/7/7-8.md`
- Run the health check: `./deployment/scripts/health-check.sh`

## Template Customization

To create a custom template:

1. Copy an existing template as a starting point
2. Modify the configuration as needed
3. Update the comments and documentation
4. Test the template with the validation script
5. Consider contributing back to the project

## Contributing

When contributing new templates:

1. Follow the naming convention: `{purpose}.env`
2. Include comprehensive comments
3. Use placeholder values for sensitive data
4. Test with the validation script
5. Update this README with template description
