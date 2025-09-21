# macOS Installation Guide

**Detailed installation procedures for macOS 12.0 (Monterey) and later**

This guide provides step-by-step installation procedures specifically optimized for macOS systems. Note that macOS is supported for development and testing only.

## 📋 Prerequisites

### System Requirements
- **macOS Version**: 12.0 (Monterey) or later
- **Architecture**: Intel x86_64 or Apple Silicon (M1/M2)
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 100GB+ available space
- **CPU**: 4+ cores recommended

### Network Requirements
- **Internet Connection**: Required for package downloads and API access
- **Ports**: 8283, 8080, 5678, 8083, 5432, 7474, 7687, 8890, 1416

## 🚀 Installation Steps

### Step 1: System Preparation

#### Install Homebrew
```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Add Homebrew to PATH
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
source ~/.zshrc

# Verify installation
brew --version
```

#### Install Essential Tools
```bash
# Install essential packages
brew install curl wget git nano htop unzip jq

# Install Docker Desktop
brew install --cask docker

# Start Docker Desktop
open /Applications/Docker.app
```

#### Configure Shell
```bash
# Set up shell environment
echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zshrc
echo 'export DOCKER_HOST=unix:///Users/$USER/.docker/run/docker.sock' >> ~/.zshrc
source ~/.zshrc
```

### Step 2: Docker Configuration

#### Verify Docker Installation
```bash
# Check Docker version
docker --version
docker compose version

# Test Docker
docker run hello-world
```

#### Configure Docker Desktop
1. Open Docker Desktop application
2. Go to Settings → Resources
3. Allocate at least 8GB RAM
4. Allocate at least 4 CPU cores
5. Enable "Use the WSL 2 based engine" (if available)

#### Configure Docker Daemon
```bash
# Create Docker daemon configuration
mkdir -p ~/.docker

# Configure Docker daemon
cat > ~/.docker/daemon.json <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
EOF
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

# Expected output: All checks should pass with macOS warnings
# Address any critical issues before proceeding
```

### Step 4: Configuration

#### Select Configuration Template
```bash
# Run template selection script
./deployment/scripts/select-template.sh

# Choose appropriate template:
# 1. Development - for local development (recommended for macOS)
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
open http://localhost:8283  # Letta
open http://localhost:8080  # Open WebUI
open http://localhost:5678  # n8n
open http://localhost:8083  # Health Monitor
```

## 🔧 macOS-Specific Configuration

### Docker Desktop Configuration

#### Resource Allocation
1. Open Docker Desktop
2. Go to Settings → Resources
3. **Memory**: Set to 8GB or more
4. **CPUs**: Set to 4 or more
5. **Disk**: Set to 100GB or more

#### Advanced Settings
1. Go to Settings → Docker Engine
2. Add the following configuration:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "live-restore": true
}
```

### Network Configuration

#### Port Forwarding
```bash
# Check port usage
lsof -i :8283
lsof -i :8080
lsof -i :5678
lsof -i :8083

# Kill conflicting processes
kill -9 [PID]
```

#### Firewall Configuration
```bash
# Check firewall status
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# Allow Docker Desktop through firewall
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /Applications/Docker.app/Contents/MacOS/Docker
```

### System Optimization

#### Kernel Parameters
```bash
# Check system limits
ulimit -a

# Increase file limits
echo 'ulimit -n 65535' >> ~/.zshrc
echo 'ulimit -u 65535' >> ~/.zshrc
source ~/.zshrc
```

#### Memory Management
```bash
# Check memory usage
vm_stat

# Monitor Docker memory usage
docker stats
```

### Service Management

#### LaunchAgent Service
```bash
# Create LaunchAgent for PA Ecosystem
mkdir -p ~/Library/LaunchAgents

# Create plist file
cat > ~/Library/LaunchAgents/com.pa-ecosystem.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.pa-ecosystem</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/docker-compose</string>
        <string>up</string>
        <string>-d</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/ai-PA</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

# Load service
launchctl load ~/Library/LaunchAgents/com.pa-ecosystem.plist
```

## 🔍 Troubleshooting

### Common macOS Issues

#### Docker Desktop Issues
```bash
# Restart Docker Desktop
osascript -e 'quit app "Docker"'
open /Applications/Docker.app

# Check Docker status
docker info
```

#### Port Conflicts
```bash
# Check port usage
lsof -i :8283
lsof -i :8080
lsof -i :5678
lsof -i :8083

# Kill conflicting processes
kill -9 [PID]

# Or change ports in .env
```

#### Permission Issues
```bash
# Fix file permissions
chmod +x deployment/deploy.sh deployment/scripts/*.sh

# Fix Docker permissions
sudo chown -R $USER ~/.docker
```

#### Service Won't Start
```bash
# Check Docker service
docker info

# Restart Docker Desktop
osascript -e 'quit app "Docker"'
open /Applications/Docker.app

# Check logs
docker-compose logs [service-name]
```

#### Resource Issues
```bash
# Check system resources
htop
df -h
vm_stat

# Clean up Docker
docker system prune -a

# Check Docker disk usage
docker system df
```

### macOS-Specific Diagnostics

#### System Information
```bash
# System information
sw_vers
uname -a
sysctl -n hw.ncpu
sysctl -n hw.memsize
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
docker-compose ps
docker stats
launchctl list | grep pa-ecosystem
```

## 🔄 Maintenance

### Regular Updates

#### System Updates
```bash
# Update system packages
brew update && brew upgrade

# Update Docker Desktop
brew upgrade --cask docker

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
# Create system backup (using Time Machine)
sudo tmutil startbackup

# Backup PA Ecosystem
./backup.sh
```

#### Recovery Procedures
```bash
# Restore from Time Machine
# Use Time Machine to restore specific files

# Restore PA Ecosystem
./deployment/scripts/restore.sh backup-file
```

## 📚 Additional Resources

### macOS Documentation
- [macOS User Guide](https://support.apple.com/guide/mac-help/)
- [Docker Desktop for Mac](https://docs.docker.com/desktop/mac/)
- [Homebrew Documentation](https://docs.brew.sh/)

### PA Ecosystem Documentation
- [Main Installation Guide](../installation-guide.md)
- [Quick Start Guide](../quick-start.md)
- [Configuration Reference](../delivery/7/7-6.md)
- [Troubleshooting Guide](../delivery/7/7-8.md)

## ⚠️ Important Notes

### Development Only
- macOS installation is intended for development and testing only
- Production deployments should use Linux servers
- Some features may not work optimally on macOS

### Performance Considerations
- Docker Desktop on macOS uses virtualization
- Performance may be slower than native Linux
- Allocate sufficient resources to Docker Desktop

### Limitations
- Some Linux-specific features may not work
- File system performance may be slower
- Network configuration may be different

---

**🎉 macOS Installation Complete!** Your PA ecosystem is now running on macOS. The system is optimized for development and testing on macOS with Docker Desktop.
