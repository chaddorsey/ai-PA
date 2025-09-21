# PA Ecosystem Troubleshooting Guide

**Comprehensive troubleshooting guide for common issues and system recovery**

This guide provides step-by-step solutions for common problems, diagnostic procedures, and recovery methods for the PA ecosystem.

## 📋 Table of Contents

1. [Quick Diagnosis](#quick-diagnosis)
2. [Common Issues](#common-issues)
3. [Service-Specific Troubleshooting](#service-specific-troubleshooting)
4. [System-Level Issues](#system-level-issues)
5. [Network Issues](#network-issues)
6. [Configuration Issues](#configuration-issues)
7. [Performance Issues](#performance-issues)
8. [Recovery Procedures](#recovery-procedures)
9. [Advanced Troubleshooting](#advanced-troubleshooting)
10. [Prevention and Best Practices](#prevention-and-best-practices)

## 🔍 Quick Diagnosis

### Diagnostic Script
```bash
# Run comprehensive diagnostics
./deployment/scripts/diagnose.sh --all

# Check specific component
./deployment/scripts/diagnose.sh letta

# System-level diagnostics
./deployment/scripts/diagnose.sh --system

# Network diagnostics
./deployment/scripts/diagnose.sh --network
```

### Health Check
```bash
# Run health check
./deployment/scripts/health-check.sh

# Check individual services
curl -f http://localhost:8283/v1/health/  # Letta
curl -f http://localhost:8080/health       # Open WebUI
curl -f http://localhost:5678/healthz      # n8n
curl -f http://localhost:8083/health       # Health Monitor
```

### Quick Status Check
```bash
# Check service status
docker-compose ps

# Check system resources
htop
df -h
free -h

# Check logs
docker-compose logs --tail=50
```

## 🐛 Common Issues

### Services Won't Start

#### Symptoms
- Docker containers exit immediately
- Services show "Exited" status
- Error messages in logs

#### Diagnosis
```bash
# Check service status
docker-compose ps

# Check service logs
docker-compose logs [service-name]

# Check Docker daemon
docker info
```

#### Solutions
```bash
# 1. Check configuration
./deployment/scripts/validate-config.sh

# 2. Check Docker resources
docker system df
docker system prune

# 3. Restart services
docker-compose down
docker-compose up -d

# 4. Check logs for specific errors
docker-compose logs [service-name] | grep -i error
```

### Port Conflicts

#### Symptoms
- Services can't bind to ports
- "Port already in use" errors
- Services won't start

#### Diagnosis
```bash
# Check port usage
lsof -i :8283
lsof -i :8080
lsof -i :5678
lsof -i :8083

# Check all ports
netstat -tlnp | grep -E "(8283|8080|5678|8083)"
```

#### Solutions
```bash
# 1. Kill conflicting processes
sudo kill -9 [PID]

# 2. Or change ports in .env
nano .env
# Update port numbers

# 3. Restart services
docker-compose restart
```

### Database Connection Issues

#### Symptoms
- Database connection errors
- Services can't connect to database
- "Connection refused" errors

#### Diagnosis
```bash
# Check database status
docker-compose ps supabase-db
docker-compose exec supabase-db pg_isready -U postgres

# Check database logs
docker-compose logs supabase-db
```

#### Solutions
```bash
# 1. Restart database
docker-compose restart supabase-db

# 2. Check database configuration
grep -E "^(POSTGRES_PASSWORD|DATABASE_URL)" .env

# 3. Wait for database to be ready
sleep 30
docker-compose exec supabase-db pg_isready -U postgres
```

### API Key Issues

#### Symptoms
- Authentication errors
- "Invalid API key" errors
- Services can't authenticate

#### Diagnosis
```bash
# Check API key configuration
grep -E "^(OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY)" .env

# Test API connectivity
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models
```

#### Solutions
```bash
# 1. Verify API key format
# OpenAI: sk-...
# Anthropic: sk-ant-...
# Gemini: AIzaSy...

# 2. Check API key validity
# Test with curl commands

# 3. Update API keys
nano .env
# Update API keys

# 4. Restart services
docker-compose restart
```

### Memory Issues

#### Symptoms
- Out of memory errors
- Services crash
- System running slowly

#### Diagnosis
```bash
# Check memory usage
free -h
docker stats

# Check system load
htop
uptime
```

#### Solutions
```bash
# 1. Increase Docker memory limits
# Edit docker-compose.yml
# Add memory limits to services

# 2. Clean up Docker
docker system prune -a

# 3. Restart services
docker-compose restart

# 4. Monitor memory usage
watch docker stats
```

## 🔧 Service-Specific Troubleshooting

### Letta AI Agent Issues

#### Service Not Responding
```bash
# Check service status
docker-compose ps letta

# Check health endpoint
curl -f http://localhost:8283/v1/health/

# Check logs
docker-compose logs letta
```

#### Common Solutions
```bash
# 1. Restart service
docker-compose restart letta

# 2. Check configuration
grep -E "^(LETTA_CHAT_MODEL|LETTA_EMBEDDING_MODEL)" .env

# 3. Check API keys
grep -E "^(OPENAI_API_KEY|ANTHROPIC_API_KEY)" .env

# 4. Check database connection
docker-compose exec supabase-db psql -U postgres -c "SELECT 1;"
```

#### Memory Issues
```bash
# Check memory usage
docker stats letta

# Increase memory limits
# Edit docker-compose.yml
# Add memory limits to letta service
```

### Open WebUI Issues

#### Web Interface Not Loading
```bash
# Check service status
docker-compose ps openwebui

# Check health endpoint
curl -f http://localhost:8080/health

# Check logs
docker-compose logs openwebui
```

#### Common Solutions
```bash
# 1. Restart service
docker-compose restart openwebui

# 2. Check configuration
grep -E "^(ENABLE_OPENAI_API|TASK_MODEL)" .env

# 3. Check API keys
grep -E "^(OPENAI_API_KEY|ANTHROPIC_API_KEY)" .env

# 4. Clear browser cache
# Clear browser cache and cookies
```

### n8n Workflow Issues

#### Workflows Not Running
```bash
# Check service status
docker-compose ps n8n

# Check health endpoint
curl -f http://localhost:5678/healthz

# Check logs
docker-compose logs n8n
```

#### Common Solutions
```bash
# 1. Restart service
docker-compose restart n8n

# 2. Check encryption key
grep N8N_ENCRYPTION_KEY .env

# 3. Check webhook URLs
grep -E "^(N8N_WEBHOOK_URL|WEBHOOK_URL)" .env

# 4. Check database connection
docker-compose exec supabase-db psql -U postgres -c "SELECT 1;"
```

### Slack Bot Issues

#### Bot Not Responding
```bash
# Check service status
docker-compose ps slackbot

# Check logs
docker-compose logs slackbot
```

#### Common Solutions
```bash
# 1. Check Slack configuration
grep -E "^(SLACK_BOT_TOKEN|SLACK_APP_TOKEN|LETTA_AGENT_ID)" .env

# 2. Verify Slack app configuration
# Check Slack app settings
# Verify bot permissions
# Check OAuth scopes

# 3. Restart service
docker-compose restart slackbot

# 4. Check Letta connection
curl -f http://localhost:8283/v1/health/
```

### Gmail MCP Server Issues

#### Email Access Issues
```bash
# Check service status
docker-compose ps gmail-mcp-server

# Check health endpoint
curl -f http://localhost:8890/health

# Check logs
docker-compose logs gmail-mcp-server
```

#### Common Solutions
```bash
# 1. Check Google OAuth configuration
grep -E "^(GOOGLE_CLIENT_ID|GOOGLE_CLIENT_SECRET)" .env

# 2. Verify OAuth setup
# Check Google Cloud Console
# Verify OAuth consent screen
# Check redirect URIs

# 3. Restart service
docker-compose restart gmail-mcp-server

# 4. Check token storage
ls -la data/google_tokens/
```

## 🖥️ System-Level Issues

### Docker Issues

#### Docker Daemon Not Running
```bash
# Check Docker status
docker info

# Start Docker daemon
sudo systemctl start docker  # Linux
# Or start Docker Desktop on macOS
```

#### Docker Permission Issues
```bash
# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Or restart session
logout
# Login again
```

#### Docker Storage Issues
```bash
# Check Docker storage
docker system df

# Clean up Docker
docker system prune -a

# Check disk space
df -h
```

### System Resource Issues

#### High CPU Usage
```bash
# Check CPU usage
htop
top

# Check Docker container CPU usage
docker stats

# Identify resource-intensive containers
docker stats --no-stream
```

#### High Memory Usage
```bash
# Check memory usage
free -h
docker stats

# Check memory limits
docker-compose config

# Adjust memory limits in docker-compose.yml
```

#### Disk Space Issues
```bash
# Check disk usage
df -h
du -sh *

# Clean up old files
docker system prune -a
rm -rf deployment/logs/*.log
```

### Operating System Issues

#### Ubuntu/Debian Issues
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Check system logs
journalctl -xe

# Check service status
systemctl status docker
```

#### CentOS/RHEL Issues
```bash
# Update system
sudo dnf update -y

# Check system logs
journalctl -xe

# Check service status
systemctl status docker
```

#### macOS Issues
```bash
# Check Docker Desktop
open /Applications/Docker.app

# Check system resources
vm_stat
df -h

# Check Docker resources
docker info
```

## 🌐 Network Issues

### Connectivity Issues

#### Local Network Issues
```bash
# Check local connectivity
ping -c 1 127.0.0.1
ping -c 1 localhost

# Check port accessibility
telnet localhost 8283
telnet localhost 8080
```

#### External Network Issues
```bash
# Check external connectivity
ping -c 1 8.8.8.8
ping -c 1 google.com

# Check DNS resolution
nslookup google.com
dig google.com
```

#### Firewall Issues
```bash
# Check firewall status
sudo ufw status  # Ubuntu/Debian
sudo firewall-cmd --list-all  # CentOS/RHEL

# Allow required ports
sudo ufw allow 8283/tcp
sudo ufw allow 8080/tcp
sudo ufw allow 5678/tcp
sudo ufw allow 8083/tcp
```

### Port Issues

#### Port Already in Use
```bash
# Find process using port
lsof -i :8283
netstat -tlnp | grep :8283

# Kill process
sudo kill -9 [PID]

# Or change port in .env
nano .env
# Update port numbers
```

#### Port Not Accessible
```bash
# Check if port is listening
netstat -tlnp | grep :8283

# Check Docker port mapping
docker-compose ps

# Check service configuration
docker-compose config
```

## ⚙️ Configuration Issues

### Environment Variable Issues

#### Missing Variables
```bash
# Check required variables
grep -E "^(OPENAI_API_KEY|POSTGRES_PASSWORD|N8N_ENCRYPTION_KEY)" .env

# Add missing variables
nano .env
# Add missing variables
```

#### Invalid Variable Values
```bash
# Validate configuration
./deployment/scripts/validate-config.sh

# Check variable formats
echo $OPENAI_API_KEY | grep -E "^sk-"
echo $ANTHROPIC_API_KEY | grep -E "^sk-ant-"
echo $GEMINI_API_KEY | grep -E "^AIzaSy"
```

#### Placeholder Values
```bash
# Check for placeholder values
grep "CHANGE_ME_" .env

# Replace placeholder values
nano .env
# Replace all CHANGE_ME_* values
```

### Docker Compose Issues

#### Configuration Errors
```bash
# Validate docker-compose.yml
docker-compose config

# Check for syntax errors
docker-compose config --quiet
```

#### Service Dependencies
```bash
# Check service dependencies
docker-compose config | grep -A 5 -B 5 "depends_on"

# Start services in order
docker-compose up -d supabase-db
sleep 10
docker-compose up -d letta
```

## ⚡ Performance Issues

### Slow Response Times

#### System Performance
```bash
# Check system load
uptime
htop

# Check I/O performance
iostat
iotop
```

#### Docker Performance
```bash
# Check Docker performance
docker stats

# Check Docker daemon logs
journalctl -u docker
```

#### Database Performance
```bash
# Check database performance
docker-compose exec supabase-db psql -U postgres -c "SELECT * FROM pg_stat_activity;"

# Check database size
docker-compose exec supabase-db psql -U postgres -c "SELECT pg_size_pretty(pg_database_size('postgres'));"
```

### Memory Leaks

#### Container Memory Usage
```bash
# Monitor memory usage
watch docker stats

# Check memory limits
docker-compose config | grep -A 5 -B 5 "memory"
```

#### System Memory Usage
```bash
# Check system memory
free -h
cat /proc/meminfo

# Check memory usage by process
ps aux --sort=-%mem | head -10
```

## 🔄 Recovery Procedures

### Service Recovery

#### Restart All Services
```bash
# Stop all services
docker-compose down

# Start all services
docker-compose up -d

# Check status
docker-compose ps
```

#### Restart Specific Service
```bash
# Restart specific service
docker-compose restart [service-name]

# Check service logs
docker-compose logs [service-name]
```

#### Recreate Service
```bash
# Recreate specific service
docker-compose up -d --force-recreate [service-name]

# Check status
docker-compose ps [service-name]
```

### Data Recovery

#### Database Recovery
```bash
# Restore from backup
./deployment/scripts/restore.sh --data-only latest

# Or restore specific database
docker-compose exec supabase-db psql -U postgres postgres < backup.sql
```

#### Configuration Recovery
```bash
# Restore configuration
./deployment/scripts/restore.sh --config-only latest

# Or restore from backup
cp backup/.env .env
```

### System Recovery

#### Complete System Recovery
```bash
# Stop all services
docker-compose down

# Restore from backup
./deployment/scripts/restore.sh --force latest

# Start services
docker-compose up -d

# Verify recovery
./deployment/scripts/health-check.sh
```

#### Emergency Recovery
```bash
# Quick configuration restore
cp deployment/backups/latest/.env .env

# Restart services
docker-compose restart

# Check status
docker-compose ps
```

## 🔧 Advanced Troubleshooting

### Log Analysis

#### Service Logs
```bash
# Check all service logs
docker-compose logs

# Check specific service logs
docker-compose logs [service-name]

# Follow logs in real-time
docker-compose logs -f [service-name]

# Check logs with timestamps
docker-compose logs -t [service-name]
```

#### System Logs
```bash
# Check system logs
journalctl -xe

# Check Docker logs
journalctl -u docker

# Check cron logs
journalctl -u cron
```

### Network Debugging

#### Network Connectivity
```bash
# Test connectivity
curl -v http://localhost:8283/v1/health/
curl -v http://localhost:8080/health
curl -v http://localhost:5678/healthz

# Check DNS resolution
nslookup localhost
dig localhost
```

#### Port Scanning
```bash
# Scan local ports
nmap -p 8283,8080,5678,8083 localhost

# Check port status
netstat -tlnp | grep -E "(8283|8080|5678|8083)"
```

### Performance Profiling

#### System Profiling
```bash
# Check system performance
htop
iotop
nethogs

# Check Docker performance
docker stats --no-stream
```

#### Application Profiling
```bash
# Check application performance
docker-compose exec [service-name] top
docker-compose exec [service-name] ps aux
```

## 📚 Prevention and Best Practices

### Regular Maintenance

#### Daily Checks
```bash
# Check service status
docker-compose ps

# Check system resources
htop
df -h

# Check logs for errors
docker-compose logs | grep -i error
```

#### Weekly Checks
```bash
# Run health check
./deployment/scripts/health-check.sh

# Check backup status
./deployment/scripts/schedule-backup.sh status

# Clean up old logs
find deployment/logs -name "*.log" -mtime +7 -delete
```

#### Monthly Checks
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Clean up Docker
docker system prune -a

# Check disk usage
df -h
du -sh *
```

### Monitoring

#### Service Monitoring
```bash
# Set up monitoring
./deployment/scripts/schedule-backup.sh install --frequency daily

# Monitor logs
tail -f deployment/logs/scheduled-backup.log
```

#### Performance Monitoring
```bash
# Monitor performance
watch docker stats

# Monitor system resources
htop
```

### Backup and Recovery

#### Regular Backups
```bash
# Set up automated backups
./deployment/scripts/schedule-backup.sh install --frequency daily --retention 30

# Test backups
./deployment/scripts/verify-backup.sh --latest
```

#### Recovery Testing
```bash
# Test recovery procedures
./deployment/scripts/restore.sh --dry-run latest

# Test emergency recovery
./deployment/scripts/restore.sh --force latest
```

---

**🆘 Still having issues?** If you can't resolve the problem using this guide, check the diagnostic script output and consider reaching out to the community for support.
