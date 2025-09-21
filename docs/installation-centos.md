# CentOS/RHEL Installation Guide

**Detailed installation procedures for CentOS 8, RHEL 8, Rocky Linux 8, and AlmaLinux 8**

This guide provides step-by-step installation procedures specifically optimized for Red Hat-based Linux distributions.

## 📋 Prerequisites

### System Requirements
- **OS**: CentOS 8, RHEL 8, Rocky Linux 8, or AlmaLinux 8
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
sudo dnf update -y

# Install essential packages
sudo dnf install -y curl wget git nano htop unzip yum-utils device-mapper-persistent-data lvm2
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
sudo localectl set-locale LANG=en_US.UTF-8
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

### Step 2: Docker Installation

#### Add Docker Repository
```bash
# Add Docker repository
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# Update package lists
sudo dnf update -y
```

#### Install Docker
```bash
# Install Docker Engine
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

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

## 🔧 CentOS/RHEL-Specific Configuration

### Firewall Configuration

#### firewalld Setup
```bash
# Enable firewalld
sudo systemctl enable firewalld
sudo systemctl start firewalld

# Allow SSH
sudo firewall-cmd --permanent --add-service=ssh

# Allow PA Ecosystem ports
sudo firewall-cmd --permanent --add-port=8283/tcp  # Letta
sudo firewall-cmd --permanent --add-port=8080/tcp  # Open WebUI
sudo firewall-cmd --permanent --add-port=5678/tcp  # n8n
sudo firewall-cmd --permanent --add-port=8083/tcp  # Health Monitor

# Reload firewall
sudo firewall-cmd --reload

# Check status
sudo firewall-cmd --list-all
```

#### Advanced Firewall Rules
```bash
# Allow specific IP ranges
sudo firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='192.168.1.0/24' port protocol='tcp' port='8283' accept"
sudo firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='10.0.0.0/8' port protocol='tcp' port='8080' accept"

# Deny external access to database ports
sudo firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='0.0.0.0/0' port protocol='tcp' port='5432' reject"
sudo firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='0.0.0.0/0' port protocol='tcp' port='7474' reject"

# Reload firewall
sudo firewall-cmd --reload
```

### SELinux Configuration

#### SELinux Setup
```bash
# Check SELinux status
sestatus

# If SELinux is enabled, configure for Docker
sudo setsebool -P container_manage_cgroup on
sudo setsebool -P container_manage_cgroup_files on

# Set SELinux context for Docker volumes
sudo setsebool -P container_manage_cgroup on
sudo chcon -Rt svirt_sandbox_file_t /var/lib/docker
```

#### SELinux Troubleshooting
```bash
# Check SELinux denials
sudo ausearch -m avc -ts recent

# Generate SELinux policy
sudo audit2allow -M dockerlocal
sudo semodule -i dockerlocal.pp
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
kernel.pid_max=4194304
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

### Common CentOS/RHEL Issues

#### Docker Permission Issues
```bash
# Fix Docker permission issues
sudo usermod -aG docker $USER
newgrp docker

# Or restart session
logout
# Login again
```

#### SELinux Issues
```bash
# Check SELinux status
sestatus

# Temporarily disable SELinux (not recommended for production)
sudo setenforce 0

# Permanently disable SELinux (edit /etc/selinux/config)
sudo nano /etc/selinux/config
# Set SELINUX=disabled
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

### CentOS/RHEL-Specific Diagnostics

#### System Information
```bash
# System information
cat /etc/os-release
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

#### Firewall Status
```bash
# Firewall status
sudo firewall-cmd --list-all
sudo firewall-cmd --list-ports
sudo firewall-cmd --list-services
```

## 🔄 Maintenance

### Regular Updates

#### System Updates
```bash
# Update system packages
sudo dnf update -y

# Update Docker
sudo dnf update docker-ce docker-ce-cli containerd.io

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
sudo tar -czf /backup/centos-system-$(date +%Y%m%d).tar.gz /etc /home /opt

# Backup PA Ecosystem
./backup.sh
```

#### Recovery Procedures
```bash
# Restore from backup
sudo tar -xzf /backup/centos-system-YYYYMMDD.tar.gz -C /

# Restore PA Ecosystem
./deployment/scripts/restore.sh backup-file
```

## 📚 Additional Resources

### CentOS/RHEL Documentation
- [CentOS Documentation](https://docs.centos.org/)
- [RHEL Documentation](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/)
- [Docker on CentOS](https://docs.docker.com/engine/install/centos/)
- [firewalld Documentation](https://firewalld.org/documentation/)

### PA Ecosystem Documentation
- [Main Installation Guide](../installation-guide.md)
- [Quick Start Guide](../quick-start.md)
- [Configuration Reference](../delivery/7/7-6.md)
- [Troubleshooting Guide](../delivery/7/7-8.md)

---

**🎉 CentOS/RHEL Installation Complete!** Your PA ecosystem is now running on CentOS/RHEL. The system is optimized for Red Hat-based distributions and includes all necessary configurations for stable operation.
