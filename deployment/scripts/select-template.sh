#!/bin/bash

# PA Ecosystem Template Selection Script
# This script helps users select the appropriate environment template

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATES_DIR="$DEPLOYMENT_DIR/templates"
PROJECT_ROOT="$(dirname "$DEPLOYMENT_DIR")"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
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

log_step() {
    echo -e "${PURPLE}[STEP]${NC} $1"
}

# Display banner
show_banner() {
    echo -e "${CYAN}"
    echo "=========================================="
    echo "  PA Ecosystem Template Selection"
    echo "=========================================="
    echo -e "${NC}"
    echo "This script helps you select the appropriate environment template"
    echo "for your PA ecosystem deployment."
    echo ""
}

# Display template options
show_template_options() {
    echo "Available templates:"
    echo ""
    echo "1. Development Template"
    echo "   - Optimized for development and testing"
    echo "   - Minimal external dependencies"
    echo "   - Debug logging enabled"
    echo "   - Local access only"
    echo ""
    echo "2. Production Template"
    echo "   - Optimized for production deployment"
    echo "   - Security-focused configuration"
    echo "   - Performance-optimized models"
    echo "   - External access ready"
    echo ""
    echo "3. Minimal Template"
    echo "   - Resource-constrained environments"
    echo "   - Minimal functionality"
    echo "   - Lightweight models"
    echo "   - Local access only"
    echo ""
    echo "4. Cloudflare Template"
    echo "   - External access via Cloudflare tunnels"
    echo "   - Production-ready with external access"
    echo "   - HTTPS configuration"
    echo "   - Domain-based access"
    echo ""
    echo "5. Local-Only Template"
    echo "   - Local development without external access"
    echo "   - All features enabled locally"
    echo "   - Debug logging enabled"
    echo "   - Optional external integrations"
    echo ""
    echo "6. Custom Template"
    echo "   - Full customization options"
    echo "   - All configuration variables available"
    echo "   - Manual configuration required"
    echo "   - Maximum flexibility"
    echo ""
}

# Get user selection
get_template_selection() {
    local selection
    while true; do
        read -p "Select template (1-6): " selection
        case $selection in
            1)
                echo "development"
                break
                ;;
            2)
                echo "production"
                break
                ;;
            3)
                echo "minimal"
                break
                ;;
            4)
                echo "cloudflare"
                break
                ;;
            5)
                echo "local-only"
                break
                ;;
            6)
                echo "custom"
                break
                ;;
            *)
                log_error "Invalid selection. Please choose 1-6."
                ;;
        esac
    done
}

# Copy template to project root
copy_template() {
    local template_name="$1"
    local template_file="$TEMPLATES_DIR/${template_name}.env"
    local target_file="$PROJECT_ROOT/.env"
    
    if [[ ! -f "$template_file" ]]; then
        log_error "Template file not found: $template_file"
        return 1
    fi
    
    log_info "Copying $template_name template to .env..."
    
    # Backup existing .env if it exists
    if [[ -f "$target_file" ]]; then
        local backup_file="${target_file}.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "Backing up existing .env to $backup_file"
        cp "$target_file" "$backup_file"
    fi
    
    # Copy template
    cp "$template_file" "$target_file"
    
    # Set secure permissions
    chmod 600 "$target_file"
    
    log_success "Template copied successfully"
}

# Show next steps
show_next_steps() {
    local template_name="$1"
    
    echo ""
    echo -e "${GREEN}=========================================="
    echo "  Template Selection Complete"
    echo "==========================================${NC}"
    echo ""
    echo "Template: $template_name"
    echo "Location: $PROJECT_ROOT/.env"
    echo ""
    echo "Next steps:"
    echo "1. Edit the .env file with your actual configuration values"
    echo "2. Replace all CHANGE_ME_* placeholders with real values"
    echo "3. Run the deployment script: ./deployment/deploy.sh"
    echo ""
    
    case "$template_name" in
        "development")
            echo "Development template notes:"
            echo "- Uses example API keys (replace with real ones)"
            echo "- Debug logging enabled"
            echo "- Local access only"
            ;;
        "production")
            echo "Production template notes:"
            echo "- All values must be replaced with real configuration"
            echo "- Uses production-grade models"
            echo "- Security-focused settings"
            ;;
        "minimal")
            echo "Minimal template notes:"
            echo "- Only essential features enabled"
            echo "- Resource-optimized configuration"
            echo "- Local access only"
            ;;
        "cloudflare")
            echo "Cloudflare template notes:"
            echo "- Configured for external access"
            echo "- Requires Cloudflare tunnel setup"
            echo "- HTTPS configuration"
            ;;
        "local-only")
            echo "Local-only template notes:"
            echo "- All features available locally"
            echo "- Debug logging enabled"
            echo "- Optional external integrations"
            ;;
        "custom")
            echo "Custom template notes:"
            echo "- Full configuration options available"
            echo "- Manual configuration required"
            echo "- Maximum flexibility"
            ;;
    esac
    
    echo ""
    echo "For detailed configuration help, see:"
    echo "- docs/delivery/7/7-6.md (Configuration Reference)"
    echo "- deployment/templates/README.md (Template Guide)"
}

# Main function
main() {
    show_banner
    show_template_options
    
    local template_name
    template_name=$(get_template_selection)
    
    log_step "Selected template: $template_name"
    
    if copy_template "$template_name"; then
        show_next_steps "$template_name"
    else
        log_error "Failed to copy template"
        exit 1
    fi
}

# Run main function
main "$@"
