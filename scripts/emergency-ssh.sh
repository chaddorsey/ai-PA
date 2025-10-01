#!/bin/bash

# Emergency SSH Access Script
# This script can be run to restore SSH access if it's disabled

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

# Check SSH status
check_ssh_status() {
    log_info "Checking SSH status..."
    
    # Check if SSH is enabled
    if sudo systemsetup -getremotelogin | grep -q "On"; then
        log_success "SSH is enabled"
        SSH_ENABLED=true
    else
        log_warning "SSH is disabled"
        SSH_ENABLED=false
    fi
    
    # Check if SSH is running
    if pgrep -x "sshd" > /dev/null; then
        log_success "SSH daemon is running"
        SSH_RUNNING=true
    else
        log_warning "SSH daemon is not running"
        SSH_RUNNING=false
    fi
}

# Enable SSH
enable_ssh() {
    if [[ "$SSH_ENABLED" == "false" ]]; then
        log_info "Enabling SSH..."
        if sudo systemsetup -setremotelogin on; then
            log_success "SSH enabled successfully"
        else
            log_error "Failed to enable SSH"
            exit 1
        fi
    fi
}

# Start SSH daemon
start_ssh() {
    if [[ "$SSH_RUNNING" == "false" ]]; then
        log_info "Starting SSH daemon..."
        if sudo launchctl load -w /System/Library/LaunchDaemons/ssh.plist; then
            log_success "SSH daemon started successfully"
        else
            log_error "Failed to start SSH daemon"
            exit 1
        fi
    fi
}

# Check SSH configuration
check_ssh_config() {
    log_info "Checking SSH configuration..."
    
    # Check if SSH config file exists
    if [[ -f /etc/ssh/sshd_config ]]; then
        log_success "SSH config file exists"
        
        # Check for common security settings
        if grep -q "PermitRootLogin no" /etc/ssh/sshd_config; then
            log_success "Root login is disabled"
        else
            log_warning "Root login may be enabled"
        fi
        
        if grep -q "PasswordAuthentication no" /etc/ssh/sshd_config; then
            log_success "Password authentication is disabled"
        else
            log_warning "Password authentication may be enabled"
        fi
    else
        log_warning "SSH config file not found"
    fi
}

# Test SSH connection
test_ssh() {
    log_info "Testing SSH connection..."
    
    # Get local IP
    LOCAL_IP=$(ifconfig | grep -E "inet.*broadcast" | awk '{print $2}' | head -1)
    
    if [[ -n "$LOCAL_IP" ]]; then
        log_info "Local IP: $LOCAL_IP"
        log_info "SSH should be accessible at: ssh $USER@$LOCAL_IP"
    else
        log_warning "Could not determine local IP"
    fi
}

# Display SSH status
display_status() {
    echo ""
    echo "=========================================="
    echo "SSH STATUS SUMMARY"
    echo "=========================================="
    echo "SSH Enabled: $SSH_ENABLED"
    echo "SSH Running: $SSH_RUNNING"
    echo "SSH Port: 22"
    echo "Local IP: $(ifconfig | grep -E "inet.*broadcast" | awk '{print $2}' | head -1)"
    echo "=========================================="
    echo ""
}

# Main execution
main() {
    echo "=========================================="
    echo "EMERGENCY SSH ACCESS SCRIPT"
    echo "=========================================="
    echo ""
    
    check_root
    check_ssh_status
    enable_ssh
    start_ssh
    check_ssh_config
    test_ssh
    display_status
    
    log_success "SSH access restored successfully!"
    log_info "You can now connect via SSH using your configured keys"
}

# Run main function
main "$@"

