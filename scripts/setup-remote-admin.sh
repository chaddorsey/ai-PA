#!/bin/bash

# Comprehensive Remote Administration Setup Script
# This script sets up all layers of remote administration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_error "This script should not be run as root"
        exit 1
    fi
}

# Check if Docker is running
check_docker() {
    log_info "Checking Docker status..."
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
    log_success "Docker is running"
}

# Check if docker-compose.yml exists
check_compose_file() {
    log_info "Checking docker-compose.yml..."
    if [[ ! -f "docker-compose.yml" ]]; then
        log_error "docker-compose.yml not found. Please run this script from the project root."
        exit 1
    fi
    log_success "docker-compose.yml found"
}

# Setup SSH access
setup_ssh() {
    log_info "Setting up SSH access..."
    
    # Check if SSH is enabled
    if sudo systemsetup -getremotelogin | grep -q "On"; then
        log_success "SSH is already enabled"
    else
        log_info "Enabling SSH..."
        sudo systemsetup -setremotelogin on
        log_success "SSH enabled"
    fi
    
    # Check if SSH key exists
    if [[ ! -f ~/.ssh/id_ed25519 ]]; then
        log_info "Creating SSH key pair..."
        ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -C "ai-pa-admin"
        log_success "SSH key pair created"
    else
        log_success "SSH key pair already exists"
    fi
    
    # Add public key to authorized_keys
    if [[ ! -f ~/.ssh/authorized_keys ]]; then
        log_info "Creating authorized_keys file..."
        touch ~/.ssh/authorized_keys
        chmod 600 ~/.ssh/authorized_keys
    fi
    
    # Add public key if not already present
    if ! grep -q "$(cat ~/.ssh/id_ed25519.pub)" ~/.ssh/authorized_keys; then
        log_info "Adding public key to authorized_keys..."
        cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
        log_success "Public key added to authorized_keys"
    else
        log_success "Public key already in authorized_keys"
    fi
}

# Setup tmux session
setup_tmux() {
    log_info "Setting up tmux session..."
    
    # Check if tmux is installed
    if ! command -v tmux &> /dev/null; then
        log_info "Installing tmux..."
        brew install tmux
    fi
    
    # Create persistent admin session
    if ! tmux has-session -t admin 2>/dev/null; then
        log_info "Creating admin tmux session..."
        tmux new-session -d -s admin
        tmux send-keys -t admin "cd /Users/dorseyhomeserver/ai-PA" Enter
        tmux send-keys -t admin "clear" Enter
        log_success "Admin tmux session created"
    else
        log_success "Admin tmux session already exists"
    fi
}

# Start remote administration services
start_admin_services() {
    log_info "Starting remote administration services..."
    
    # Start RustDesk services
    log_info "Starting RustDesk services..."
    docker-compose up -d rustdesk-hbbs rustdesk-hbbr
    
    # Start web-based admin tools
    log_info "Starting web-based administration tools..."
    docker-compose up -d portainer cockpit
    
    # Wait for services to start
    log_info "Waiting for services to start..."
    sleep 30
    
    # Verify services
    log_info "Verifying services..."
    docker-compose ps rustdesk-hbbs rustdesk-hbbr portainer cockpit
}

# Get RustDesk public key
get_rustdesk_key() {
    log_info "Retrieving RustDesk public key..."
    
    # Wait for key to be generated
    sleep 10
    
    if docker exec rustdesk-hbbs test -f /root/id_ed25519.pub; then
        PUBLIC_KEY=$(docker exec rustdesk-hbbs cat /root/id_ed25519.pub)
        log_success "Public key retrieved successfully"
    else
        log_error "Public key not found. The service may not have started properly."
        return 1
    fi
}

# Make scripts executable
make_scripts_executable() {
    log_info "Making scripts executable..."
    
    local scripts=(
        "scripts/emergency-ssh.sh"
        "scripts/system-recovery.sh"
        "scripts/setup-rustdesk.sh"
    )
    
    for script in "${scripts[@]}"; do
        if [[ -f "$script" ]]; then
            chmod +x "$script"
            log_success "Made $script executable"
        else
            log_warning "Script $script not found"
        fi
    done
}

# Display connection information
show_connection_info() {
    log_info "Gathering connection information..."
    
    # Get local IP
    LOCAL_IP=$(ifconfig | grep -E "inet.*broadcast" | awk '{print $2}' | head -1)
    
    echo ""
    echo "=========================================="
    echo "REMOTE ADMINISTRATION ACCESS INFORMATION"
    echo "=========================================="
    echo ""
    echo "SSH Access:"
    echo "  Command: ssh $USER@$LOCAL_IP"
    echo "  Key: ~/.ssh/id_ed25519"
    echo ""
    echo "RustDesk Access:"
    echo "  ID Server: $LOCAL_IP:21116"
    echo "  Relay Server: $LOCAL_IP:21117"
    echo "  Web Client: http://$LOCAL_IP:21118"
    echo "  Public Key: $PUBLIC_KEY"
    echo ""
    echo "Web-based Administration:"
    echo "  Portainer: http://$LOCAL_IP:9000"
    echo "  Cockpit: http://$LOCAL_IP:9090"
    echo ""
    echo "External Access (via Cloudflare):"
    echo "  RustDesk: rustdesk.cd-ai-pa.work:21116"
    echo "  Portainer: portainer.cd-ai-pa.work"
    echo "  Cockpit: cockpit.cd-ai-pa.work"
    echo ""
    echo "Emergency Scripts:"
    echo "  SSH Recovery: ./scripts/emergency-ssh.sh"
    echo "  System Recovery: ./scripts/system-recovery.sh"
    echo "  RustDesk Setup: ./scripts/setup-rustdesk.sh"
    echo "=========================================="
    echo ""
}

# Display next steps
show_next_steps() {
    echo ""
    echo "=========================================="
    echo "NEXT STEPS"
    echo "=========================================="
    echo "1. Test SSH access: ssh $USER@$LOCAL_IP"
    echo "2. Download RustDesk client from: https://rustdesk.com"
    echo "3. Configure RustDesk with the connection information above"
    echo "4. Access web-based tools:"
    echo "   - Portainer: http://$LOCAL_IP:9000"
    echo "   - Cockpit: http://$LOCAL_IP:9090"
    echo "5. Test emergency scripts"
    echo "6. Configure Cloudflare tunnel for external access"
    echo ""
    echo "For detailed instructions, see: docs/remote-administration-strategy.md"
    echo "=========================================="
    echo ""
}

# Main execution
main() {
    echo "=========================================="
    echo "COMPREHENSIVE REMOTE ADMINISTRATION SETUP"
    echo "=========================================="
    echo ""
    
    # Change to project root
    cd "$(dirname "$0")/.."
    
    # Run setup steps
    check_root
    check_docker
    check_compose_file
    setup_ssh
    setup_tmux
    start_admin_services
    get_rustdesk_key
    make_scripts_executable
    show_connection_info
    show_next_steps
    
    log_success "Remote administration setup completed successfully!"
    log_info "You now have multiple layers of remote access to your system"
}

# Run main function
main "$@"

