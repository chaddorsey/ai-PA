# Troubleshooting Quick Reference

**Quick reference for common issues and solutions**

## 🚨 Emergency Procedures

### System Down
```bash
# 1. Check service status
docker-compose ps

# 2. Restart all services
docker-compose down && docker-compose up -d

# 3. Check health
./deployment/scripts/health-check.sh
```

### Services Not Responding
```bash
# 1. Check logs
docker-compose logs --tail=50

# 2. Restart specific service
docker-compose restart [service-name]

# 3. Check configuration
./deployment/scripts/validate-config.sh
```

### Database Issues
```bash
# 1. Check database status
docker-compose exec supabase-db pg_isready -U postgres

# 2. Restart database
docker-compose restart supabase-db

# 3. Wait and check again
sleep 30 && docker-compose exec supabase-db pg_isready -U postgres
```

## 🔍 Quick Diagnostics

### Run Full Diagnostics
```bash
./deployment/scripts/diagnose.sh --all
```

### Check Specific Component
```bash
./deployment/scripts/diagnose.sh letta
./deployment/scripts/diagnose.sh openwebui
./deployment/scripts/diagnose.sh n8n
```

### Check System Health
```bash
./deployment/scripts/health-check.sh
```

## 🐛 Common Issues

### Port Conflicts
```bash
# Find process using port
lsof -i :8283

# Kill process
sudo kill -9 [PID]

# Or change port in .env
nano .env
```

### API Key Issues
```bash
# Check API keys
grep -E "^(OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY)" .env

# Test API connectivity
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
```

### Memory Issues
```bash
# Check memory usage
docker stats

# Clean up Docker
docker system prune -a

# Restart services
docker-compose restart
```

### Configuration Issues
```bash
# Validate configuration
./deployment/scripts/validate-config.sh

# Check for placeholder values
grep "CHANGE_ME_" .env

# Replace placeholders
nano .env
```

## 🔧 Service-Specific Issues

### Letta AI Agent
```bash
# Check status
curl -f http://localhost:8283/v1/health/

# Check logs
docker-compose logs letta

# Restart
docker-compose restart letta
```

### Open WebUI
```bash
# Check status
curl -f http://localhost:8080/health

# Check logs
docker-compose logs openwebui

# Restart
docker-compose restart openwebui
```

### n8n Workflows
```bash
# Check status
curl -f http://localhost:5678/healthz

# Check logs
docker-compose logs n8n

# Restart
docker-compose restart n8n
```

### Slack Bot
```bash
# Check logs
docker-compose logs slackbot

# Check configuration
grep -E "^(SLACK_BOT_TOKEN|SLACK_APP_TOKEN|LETTA_AGENT_ID)" .env

# Restart
docker-compose restart slackbot
```

## 🌐 Network Issues

### Local Connectivity
```bash
# Test local ports
curl -f http://localhost:8283/v1/health/
curl -f http://localhost:8080/health
curl -f http://localhost:5678/healthz
curl -f http://localhost:8083/health
```

### External Connectivity
```bash
# Test external access
ping -c 1 8.8.8.8
ping -c 1 google.com

# Test DNS
nslookup google.com
```

### Firewall Issues
```bash
# Check firewall (Ubuntu/Debian)
sudo ufw status

# Allow ports
sudo ufw allow 8283/tcp
sudo ufw allow 8080/tcp
sudo ufw allow 5678/tcp
sudo ufw allow 8083/tcp
```

## ⚡ Performance Issues

### High CPU Usage
```bash
# Check CPU usage
htop
docker stats

# Identify resource-intensive containers
docker stats --no-stream
```

### High Memory Usage
```bash
# Check memory usage
free -h
docker stats

# Clean up Docker
docker system prune -a
```

### Disk Space Issues
```bash
# Check disk usage
df -h
du -sh *

# Clean up old files
docker system prune -a
rm -rf deployment/logs/*.log
```

## 🔄 Recovery Procedures

### Restart All Services
```bash
docker-compose down
docker-compose up -d
```

### Restore from Backup
```bash
# Restore latest backup
./deployment/scripts/restore.sh --force latest

# Restore specific backup
./deployment/scripts/restore.sh --force /backups/backup-YYYYMMDD_HHMMSS
```

### Emergency Configuration
```bash
# Restore configuration only
./deployment/scripts/restore.sh --config-only latest

# Or manually restore
cp deployment/backups/latest/.env .env
```

## 📊 Monitoring Commands

### Service Status
```bash
# Check all services
docker-compose ps

# Check specific service
docker-compose ps [service-name]
```

### System Resources
```bash
# Check system resources
htop
df -h
free -h

# Check Docker resources
docker stats
```

### Logs
```bash
# Check all logs
docker-compose logs

# Check specific service logs
docker-compose logs [service-name]

# Follow logs in real-time
docker-compose logs -f [service-name]
```

## 🆘 When to Get Help

### Check These First
1. **Run diagnostics**: `./deployment/scripts/diagnose.sh --all`
2. **Check logs**: `docker-compose logs --tail=50`
3. **Validate configuration**: `./deployment/scripts/validate-config.sh`
4. **Check system resources**: `htop`, `df -h`, `free -h`

### Provide This Information
1. **Diagnostic output**: `./deployment/scripts/diagnose.sh --all > diagnostic.txt`
2. **Service logs**: `docker-compose logs > service-logs.txt`
3. **System information**: `uname -a`, `docker --version`
4. **Configuration**: `cat .env` (remove sensitive data)

### Common Error Messages
- **"Port already in use"**: Kill conflicting process or change port
- **"Connection refused"**: Check service status and configuration
- **"Invalid API key"**: Check API key format and validity
- **"Out of memory"**: Increase memory limits or clean up resources
- **"Permission denied"**: Check file permissions and Docker permissions

---

**💡 Pro Tip**: Always run `./deployment/scripts/diagnose.sh --all` first to get a comprehensive system overview before troubleshooting specific issues.
