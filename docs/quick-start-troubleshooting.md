# Quick Start: Troubleshooting Guide

**Quick solutions to common deployment issues**

This guide provides fast solutions to the most common issues encountered during PA ecosystem deployment.

## 🚨 Emergency Quick Fixes

### System Won't Start
```bash
# Quick restart
docker-compose down && docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs
```

### Services Unhealthy
```bash
# Health check
./deployment/scripts/health-check.sh

# Restart unhealthy services
docker-compose restart [service-name]

# Full restart
docker-compose restart
```

### Configuration Issues
```bash
# Validate configuration
./deployment/scripts/validate-config.sh

# Reset to template
./deployment/scripts/select-template.sh
```

## 🔍 Common Issues & Solutions

### 1. System Requirements Issues

#### "Insufficient disk space"
```bash
# Check disk space
df -h

# Free up space
sudo apt autoremove -y
docker system prune -a
sudo rm -rf /var/log/*.log

# Minimum required: 100GB
```

#### "Insufficient RAM"
```bash
# Check RAM usage
free -h

# Free up RAM
sudo sync
echo 3 | sudo tee /proc/sys/vm/drop_caches

# Minimum required: 8GB
```

#### "Docker not installed"
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Log out and back in
```

### 2. Configuration Issues

#### "Required variable not set"
```bash
# Check .env file
cat .env | grep -E "(OPENAI_API_KEY|POSTGRES_PASSWORD|N8N_ENCRYPTION_KEY)"

# Fix missing variables
nano .env
# Add missing variables with proper values
```

#### "API key format invalid"
```bash
# Check API key formats
echo "OpenAI: $OPENAI_API_KEY" | head -c 20
echo "Anthropic: $ANTHROPIC_API_KEY" | head -c 20
echo "Gemini: $GEMINI_API_KEY" | head -c 20

# Fix formats:
# OpenAI: sk-...
# Anthropic: sk-ant-...
# Gemini: AIzaSy...
```

#### "Password too short"
```bash
# Generate strong password
openssl rand -base64 32

# Update .env
nano .env
# Set POSTGRES_PASSWORD=generated-password
```

### 3. Service Issues

#### "Service won't start"
```bash
# Check service logs
docker-compose logs [service-name]

# Common fixes:
# - Check port conflicts: lsof -i :PORT
# - Check resource limits: docker stats
# - Restart Docker: sudo systemctl restart docker
```

#### "Port already in use"
```bash
# Find what's using the port
lsof -i :8283
lsof -i :8080
lsof -i :5678

# Kill the process
sudo kill -9 [PID]

# Or change port in .env
```

#### "Database connection failed"
```bash
# Check database service
docker-compose ps supabase-db

# Check database logs
docker-compose logs supabase-db

# Restart database
docker-compose restart supabase-db
```

### 4. Network Issues

#### "Can't access web interfaces"
```bash
# Check if services are running
docker-compose ps

# Check if ports are open
netstat -tlnp | grep -E "(8283|8080|5678)"

# Test local access
curl -f http://localhost:8283/v1/health/
```

#### "External access not working"
```bash
# Check Cloudflare tunnel
docker-compose logs cloudflare-tunnel

# Test external URLs
curl -f https://your-domain.com/health

# Check DNS
nslookup your-domain.com
```

### 5. API Issues

#### "OpenAI API errors"
```bash
# Test API key
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models

# Check API key format
echo $OPENAI_API_KEY | grep -E "^sk-"

# Check API limits
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/usage
```

#### "Rate limit exceeded"
```bash
# Wait and retry
sleep 60
docker-compose restart letta

# Check usage
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/usage
```

### 6. Performance Issues

#### "System running slowly"
```bash
# Check resource usage
docker stats
htop
df -h

# Free up resources
docker system prune -a
sudo apt autoremove -y
```

#### "High memory usage"
```bash
# Check memory usage
free -h
docker stats

# Restart services
docker-compose restart

# Check for memory leaks
docker-compose logs | grep -i memory
```

## 🔧 Diagnostic Commands

### System Health
```bash
# Overall health
./deployment/scripts/health-check.sh

# System resources
htop
df -h
free -h
nproc

# Docker status
docker ps -a
docker stats
docker system df
```

### Service Status
```bash
# All services
docker-compose ps

# Specific service
docker-compose ps [service-name]

# Service logs
docker-compose logs [service-name]
docker-compose logs -f [service-name]
```

### Configuration
```bash
# Validate config
./deployment/scripts/validate-config.sh

# Check .env
cat .env | grep -v "^#"

# Test API keys
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models
```

### Network
```bash
# Port usage
netstat -tlnp | grep -E "(8283|8080|5678|8083)"

# Test connectivity
curl -f http://localhost:8283/v1/health/
curl -f http://localhost:8080/health
curl -f http://localhost:5678/healthz

# External access
curl -f https://your-domain.com/health
```

## 🚑 Emergency Recovery

### Complete Reset
```bash
# Stop all services
docker-compose down

# Remove all containers and volumes
docker-compose down -v
docker system prune -a

# Restore from backup
cp .env.backup.YYYYMMDD_HHMMSS .env

# Redeploy
./deployment/deploy.sh
```

### Rollback Deployment
```bash
# Use rollback script
./deployment/scripts/rollback.sh

# Or manual rollback
docker-compose down
git checkout HEAD~1
./deployment/deploy.sh
```

### Restore from Backup
```bash
# List available backups
ls -la backups/

# Restore configuration
cp backups/config-YYYYMMDD-HHMMSS.env .env

# Restore database
docker-compose exec supabase-db psql -U postgres < backups/database-YYYYMMDD-HHMMSS.sql

# Restart services
docker-compose restart
```

## 📞 Getting Help

### Self-Help Resources
1. **Check logs**: `docker-compose logs [service-name]`
2. **Run health check**: `./deployment/scripts/health-check.sh`
3. **Validate config**: `./deployment/scripts/validate-config.sh`
4. **Check system resources**: `htop`, `df -h`, `free -h`

### Documentation
- **Main Quick Start**: [quick-start.md](./quick-start.md)
- **Configuration Reference**: [delivery/7/7-6.md](./delivery/7/7-6.md)
- **Detailed Troubleshooting**: [delivery/7/7-8.md](./delivery/7/7-8.md)

### Community Support
- **GitHub Issues**: Report bugs and request help
- **Discord/Slack**: Community support channels
- **Documentation**: Comprehensive guides in `docs/`

## 🎯 Quick Success Checklist

### Before Deployment
- [ ] System meets minimum requirements
- [ ] Docker and Docker Compose installed
- [ ] API keys obtained and valid
- [ ] Sufficient disk space (100GB+)
- [ ] Sufficient RAM (8GB+)

### During Deployment
- [ ] All validation checks pass
- [ ] No error messages in logs
- [ ] Services start successfully
- [ ] Health checks pass
- [ ] Web interfaces accessible

### After Deployment
- [ ] All services running (`docker-compose ps`)
- [ ] Health check passes (`./deployment/scripts/health-check.sh`)
- [ ] Web interfaces work
- [ ] AI responds to queries
- [ ] No error messages in logs

## 🔄 Prevention Tips

### Regular Maintenance
```bash
# Daily
./deployment/scripts/health-check.sh

# Weekly
docker-compose logs --since=7d
docker system prune

# Monthly
sudo apt update && sudo apt upgrade -y
./deployment/scripts/backup.sh
```

### Monitoring
```bash
# Set up monitoring
echo "*/5 * * * * /path/to/ai-PA/deployment/scripts/health-check.sh" | crontab -

# Monitor resources
watch docker stats
```

### Backup Strategy
```bash
# Regular backups
./deployment/scripts/backup.sh

# Test restore
./deployment/scripts/restore.sh backup-file
```

---

**🆘 Still having issues?** Check the detailed troubleshooting guide in `docs/delivery/7/7-8.md` or reach out to the community for support.
