# Ubuntu Installation Guide

**Detailed installation procedures for Ubuntu 20.04 LTS and 22.04 LTS**

This guide provides step-by-step installation procedures specifically optimized for Ubuntu systems.

## 📋 Prerequisites

### System Requirements
- **Ubuntu Version**: 20.04 LTS or 22.04 LTS
- **Architecture**: x86_64 (AMD64)
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 100GB+ available space
- **CPU**: 4+ cores recommended

### Network Requirements
- **Internet Connection**: Required for package downloads and API access
- **Ports**: 8283, 8080, 5678, 8083, 5432, 7474, 7687, 8890, 1416

## 🚀 Installation Steps

### Step 1: System Preparation

#### Update System Packages
```bash
# Update package lists
sudo apt update

# Upgrade installed packages
sudo apt upgrade -y

# Install essential packages
sudo apt install -y curl wget git nano htop unzip software-properties-common apt-transport-https ca-certificates gnupg lsb-release
```

#### Configure Timezone
```bash
# Set timezone
sudo timedatectl set-timezone UTC

# Verify timezone
timedatectl status
```

#### Configure Locale
```bash
# Set locale
sudo locale-gen en_US.UTF-8
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

### Step 2: Docker Installation

#### Add Docker Repository
```bash
# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package lists
sudo apt update
```

#### Install Docker
```bash
# Install Docker Engine
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add current user to docker group
sudo usermod -aG docker $USER

# Enable Docker service
sudo systemctl enable docker
sudo systemctl start docker

# Verify installation
docker --version
docker compose version
```

#### Configure Docker
```bash
# Create Docker daemon configuration
sudo mkdir -p /etc/docker

# Configure Docker daemon
sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "live-restore": true
}
EOF

# Restart Docker service
sudo systemctl restart docker
```

### Step 3: Repository Setup

#### Clone Repository
```bash
# Clone the repository
git clone https://github.com/your-org/ai-PA.git
cd ai-PA

# Make scripts executable
chmod +x deployment/deploy.sh deployment/scripts/*.sh

# Create necessary directories
mkdir -p deployment/logs deployment/config deployment/backups
```

#### Verify System Requirements
```bash
# Run system requirements validation
./deployment/scripts/validate-requirements.sh

# Expected output: All checks should pass
# If any fail, address them before proceeding
```

### Step 4: Configuration

#### Select Configuration Template
```bash
# Run template selection script
./deployment/scripts/select-template.sh

# Choose appropriate template:
# 1. Development - for local development
# 2. Production - for production deployment
# 3. Minimal - for resource-constrained environments
# 4. Cloudflare - for external access via Cloudflare
# 5. Local-Only - for local development with all features
# 6. Custom - for maximum customization
```

#### Configure Environment
```bash
# Edit configuration file
nano .env

# Required configuration changes:
# - Replace all CHANGE_ME_* placeholders
# - Set your API keys
# - Configure passwords (minimum 32 characters)
# - Set webhook URLs if using external access
```

#### Validate Configuration
```bash
# Validate configuration
./deployment/scripts/validate-config.sh

# Expected output: All validation checks should pass
# Address any warnings or errors before proceeding
```

### Step 5: Service Deployment

#### Deploy Services
```bash
# Deploy all services
./deployment/deploy.sh

# Or deploy with specific options:
# ./deployment/deploy.sh --non-interactive  # Automated deployment
# ./deployment/deploy.sh --quick           # Quick deployment
# ./deployment/deploy.sh --dry-run         # Preview deployment
```

#### Monitor Deployment
```bash
# Watch deployment progress
docker-compose logs -f

# Check service status
docker-compose ps

# Expected output: All services should be "Up"
```

### Step 6: Verification

#### Health Check
```bash
# Run comprehensive health check
./deployment/scripts/health-check.sh

# Expected output:
# Total checks: 18
# Passed: 16
# Failed: 0
# Warnings: 2
```

#### Service Verification
```bash
# Check individual services
curl -f http://localhost:8283/v1/health/  # Letta
curl -f http://localhost:8080/health       # Open WebUI
curl -f http://localhost:5678/healthz      # n8n
curl -f http://localhost:8083/health       # Health Monitor
```

#### Access Web Interfaces
```bash
# Open web interfaces
xdg-open http://localhost:8283  # Letta
xdg-open http://localhost:8080  # Open WebUI
xdg-open http://localhost:5678  # n8n
xdg-open http://localhost:8083  # Health Monitor
```

## 🔧 Ubuntu-Specific Configuration

### Firewall Configuration

#### UFW Setup
```bash
# Enable UFW
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Allow PA Ecosystem ports
sudo ufw allow 8283/tcp  # Letta
sudo ufw allow 8080/tcp  # Open WebUI
sudo ufw allow 5678/tcp  # n8n
sudo ufw allow 8083/tcp  # Health Monitor

# Check status
sudo ufw status
```

#### Advanced Firewall Rules
```bash
# Allow specific IP ranges
sudo ufw allow from 192.168.1.0/24 to any port 8283
sudo ufw allow from 10.0.0.0/8 to any port 8080

# Deny external access to database ports
sudo ufw deny 5432/tcp
sudo ufw deny 7474/tcp
sudo ufw deny 7687/tcp
```

### System Optimization

#### Kernel Parameters
```bash
# Optimize kernel parameters
sudo tee -a /etc/sysctl.conf > /dev/null <<EOF
# PA Ecosystem optimizations
vm.max_map_count=262144
net.core.somaxconn=65535
net.ipv4.tcp_max_syn_backlog=65535
net.core.netdev_max_backlog=5000
EOF

# Apply changes
sudo sysctl -p
```

#### File Limits
```bash
# Increase file limits
sudo tee -a /etc/security/limits.conf > /dev/null <<EOF
# PA Ecosystem file limits
* soft nofile 65535
* hard nofile 65535
* soft nproc 65535
* hard nproc 65535
EOF
```

### Service Management

#### Systemd Service
```bash
# Create systemd service for PA Ecosystem
sudo tee /etc/systemd/system/pa-ecosystem.service > /dev/null <<EOF
[Unit]
Description=PA Ecosystem
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/path/to/ai-PA
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable pa-ecosystem.service
```

#### Auto-start Configuration
```bash
# Start services on boot
sudo systemctl start pa-ecosystem.service

# Check status
sudo systemctl status pa-ecosystem.service
```

## 🔍 Troubleshooting

### Common Ubuntu Issues

#### Docker Permission Issues
```bash
# Fix Docker permission issues
sudo usermod -aG docker $USER
newgrp docker

# Or restart session
logout
# Login again
```

#### Port Conflicts
```bash
# Check port usage
sudo netstat -tlnp | grep -E "(8283|8080|5678|8083)"

# Kill conflicting processes
sudo kill -9 [PID]

# Or change ports in .env
```

#### Service Won't Start
```bash
# Check Docker service
sudo systemctl status docker

# Restart Docker
sudo systemctl restart docker

# Check logs
docker-compose logs [service-name]
```

#### Resource Issues
```bash
# Check system resources
htop
df -h
free -h

# Clean up Docker
docker system prune -a

# Check disk space
sudo du -sh /var/lib/docker
```

### Ubuntu-Specific Diagnostics

#### System Information
```bash
# System information
lsb_release -a
uname -a
lscpu
free -h
df -h
```

#### Docker Information
```bash
# Docker information
docker --version
docker compose version
docker info
docker system df
```

#### Service Status
```bash
# Service status
sudo systemctl status docker
docker-compose ps
docker stats
```

## 🔄 Maintenance

### Regular Updates

#### System Updates
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Docker
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io

# Restart services
docker-compose restart
```

#### Application Updates
```bash
# Pull latest changes
git pull origin main

# Update services
docker-compose pull
docker-compose up -d

# Verify update
./deployment/scripts/health-check.sh
```

### Backup and Recovery

#### System Backup
```bash
# Create system backup
sudo tar -czf /backup/ubuntu-system-$(date +%Y%m%d).tar.gz /etc /home /opt

# Backup PA Ecosystem
./backup.sh
```

#### Recovery Procedures
```bash
# Restore from backup
sudo tar -xzf /backup/ubuntu-system-YYYYMMDD.tar.gz -C /

# Restore PA Ecosystem
./deployment/scripts/restore.sh backup-file
```

## 📚 Additional Resources

### Ubuntu Documentation
- [Ubuntu Server Guide](https://ubuntu.com/server/docs)
- [Docker on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [UFW Firewall](https://help.ubuntu.com/community/UFW)

### PA Ecosystem Documentation
- [Main Installation Guide](../installation-guide.md)
- [Quick Start Guide](../quick-start.md)
- [Configuration Reference](../delivery/7/7-6.md)
- [Troubleshooting Guide](../delivery/7/7-8.md)

---

**🎉 Ubuntu Installation Complete!** Your PA ecosystem is now running on Ubuntu. The system is optimized for Ubuntu and includes all necessary configurations for stable operation.
