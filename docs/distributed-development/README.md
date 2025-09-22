# Distributed Development Workflow

This document describes the simplified distributed development workflow for the PA ecosystem, optimized for single semi-technical developers.

## Overview

The distributed development workflow allows you to:
- Develop and test on your laptop while production runs on the server
- Deploy staging environments on both laptop and server
- Synchronize production data to staging for realistic testing
- Deploy upgrades with automated validation and rollback

## Quick Start

### 1. Deploy Staging Environment

```bash
# Deploy staging environment (auto-detects laptop vs server)
./scripts/deploy-staging.sh

# Or specify environment explicitly
./scripts/deploy-staging.sh --env laptop
./scripts/deploy-staging.sh --env server
```

### 2. Sync Production Data

```bash
# Sync production data to staging
./scripts/sync-production-data.sh
```

### 3. Test Your Changes

```bash
# Run health checks
./scripts/health-check.sh --staging

# Run workflow tests
./scripts/test-workflows.sh --staging
```

### 4. Deploy to Production

```bash
# Promote staging to production
./scripts/promote-to-production.sh
```

### 5. Rollback if Needed

```bash
# List available rollback points
./scripts/rollback.sh --list

# Rollback to specific tag
./scripts/rollback.sh --tag rollback-20250121-143000

# Emergency rollback
./scripts/rollback.sh --emergency
```

## Architecture

### Environment Configuration

The system uses three environment configurations:

- **Production** (`docker-compose.yml`): Live production environment
- **Staging** (`docker-compose.staging.yml`): Testing environment
- **Environment-specific** (`.env` files): Configuration overrides

### Key Components

1. **Docker Compose Templates**: Portable staging environment
2. **Data Synchronization**: Database dumps and file sync
3. **Automated Testing**: Health checks and workflow validation
4. **Deployment Scripts**: Git-based deployment and rollback
5. **Documentation**: Comprehensive guides and troubleshooting

## Detailed Workflows

### Laptop Development Workflow

1. **Start Development**:
   ```bash
   # Deploy staging environment on laptop
   ./scripts/deploy-staging.sh --env laptop
   ```

2. **Sync Production Data**:
   ```bash
   # Get realistic data for testing
   ./scripts/sync-production-data.sh
   ```

3. **Develop and Test**:
   ```bash
   # Make your changes
   # Test locally
   ./scripts/health-check.sh --staging
   ./scripts/test-workflows.sh --staging
   ```

4. **Commit Changes**:
   ```bash
   git add .
   git commit -m "Feature: new functionality"
   git push origin feature-branch
   ```

### Server Deployment Workflow

1. **Deploy Staging on Server**:
   ```bash
   # Deploy staging environment on server
   ./scripts/deploy-staging.sh --env server
   ```

2. **Test on Server**:
   ```bash
   # Run comprehensive tests
   ./scripts/health-check.sh --staging
   ./scripts/test-workflows.sh --staging
   ```

3. **Promote to Production**:
   ```bash
   # Deploy to production with validation
   ./scripts/promote-to-production.sh
   ```

### Rollback Workflow

1. **List Rollback Points**:
   ```bash
   ./scripts/rollback.sh --list
   ```

2. **Perform Rollback**:
   ```bash
   # Rollback to specific tag
   ./scripts/rollback.sh --tag rollback-20250121-143000
   
   # Or emergency rollback
   ./scripts/rollback.sh --emergency
   ```

## Scripts Reference

### Core Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `deploy-staging.sh` | Deploy staging environment | `./scripts/deploy-staging.sh [--env laptop|server]` |
| `sync-production-data.sh` | Sync production data to staging | `./scripts/sync-production-data.sh` |
| `promote-to-production.sh` | Deploy staging to production | `./scripts/promote-to-production.sh` |
| `rollback.sh` | Rollback to previous version | `./scripts/rollback.sh [--tag <tag>]` |

### Testing Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `health-check.sh` | Check service health | `./scripts/health-check.sh [--staging|--production]` |
| `test-workflows.sh` | Test critical workflows | `./scripts/test-workflows.sh [--staging|--production]` |

## Configuration

### Environment Variables

The system uses environment-specific `.env` files:

- **Production**: Uses existing production configuration
- **Staging**: Generated automatically with staging-specific settings
- **Laptop**: Includes resource constraints and debug settings

### Port Configuration

| Service | Production | Staging | Laptop |
|---------|------------|---------|--------|
| Letta | 8283 | 8283 | 8283 |
| Open WebUI | 8080 | 8080 | 8080 |
| n8n | 5678 | 5678 | 5678 |
| Database | Internal | 5432 | 5432 |
| Neo4j | Internal | 7474 | 7474 |

## Troubleshooting

### Common Issues

1. **Staging Environment Won't Start**:
   ```bash
   # Check Docker status
   docker ps
   
   # Check logs
   docker-compose -f docker-compose.staging.yml logs
   
   # Restart staging
   ./scripts/deploy-staging.sh
   ```

2. **Data Sync Fails**:
   ```bash
   # Check production environment
   docker-compose ps
   
   # Check staging data directory
   ls -la staging-data/
   
   # Re-run sync
   ./scripts/sync-production-data.sh
   ```

3. **Health Checks Fail**:
   ```bash
   # Run detailed health check
   ./scripts/health-check.sh --staging --verbose
   
   # Check specific service
   docker-compose -f docker-compose.staging.yml logs <service-name>
   ```

4. **Rollback Issues**:
   ```bash
   # List available rollback points
   ./scripts/rollback.sh --list
   
   # Check Git status
   git status
   git log --oneline -10
   ```

### Log Files

All scripts generate detailed logs:

- **Deployment logs**: `logs/staging/deploy-YYYYMMDD.log`
- **Sync logs**: `logs/staging/sync-YYYYMMDD.log`
- **Health check logs**: `logs/health/health-check-YYYYMMDD.log`
- **Test logs**: `logs/testing/workflow-test-YYYYMMDD.log`

### Debug Mode

Enable debug mode for detailed output:

```bash
# Set debug environment variable
export DEBUG=true

# Run scripts with debug output
./scripts/deploy-staging.sh
./scripts/health-check.sh --staging
```

## Best Practices

### Development

1. **Always test on staging first**
2. **Sync production data regularly for realistic testing**
3. **Use Git tags for rollback points**
4. **Keep staging environment clean and up-to-date**

### Deployment

1. **Run health checks before promotion**
2. **Test workflows thoroughly**
3. **Monitor deployment progress**
4. **Have rollback plan ready**

### Maintenance

1. **Regular health checks**
2. **Clean up old backups and logs**
3. **Update documentation**
4. **Monitor resource usage**

## Security Considerations

### Data Sanitization

On laptop environments, sensitive data is automatically sanitized:
- Email addresses replaced with test@example.com
- Phone numbers replaced with 555-0123
- Names replaced with Test User

### Access Control

- Staging environments use internal networks
- External access only via designated ports
- Production data access requires proper authentication

### Backup and Recovery

- Automatic backups before production deployment
- Git-based version control for code changes
- Database and volume backups for data recovery

## Performance Optimization

### Laptop Environments

- Resource constraints applied automatically
- Debug mode enabled for development
- Reduced logging for better performance

### Server Environments

- Full resource allocation
- Production-optimized settings
- Comprehensive monitoring

## Monitoring and Alerting

### Health Monitoring

- Automated health checks every 30 seconds
- Service status monitoring
- Resource usage tracking

### Log Monitoring

- Centralized logging
- Error detection and alerting
- Performance metrics collection

## Support and Maintenance

### Regular Tasks

1. **Weekly**: Run health checks and cleanup
2. **Monthly**: Update documentation and test procedures
3. **Quarterly**: Review and optimize performance

### Emergency Procedures

1. **Service Down**: Check health status and restart
2. **Data Loss**: Restore from backup
3. **Deployment Failure**: Rollback to previous version

## Conclusion

This distributed development workflow provides a simple, reliable way to develop and deploy the PA ecosystem across laptop and server environments. The system is designed to be maintainable by a single semi-technical developer while providing enterprise-grade reliability and rollback capabilities.

For additional support or questions, refer to the troubleshooting section or check the log files for detailed error information.
