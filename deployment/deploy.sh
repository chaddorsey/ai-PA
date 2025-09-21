#!/bin/bash

# PA Ecosystem Deployment Script
# This script orchestrates the complete deployment of the Personal Assistant ecosystem

set -uo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOYMENT_DIR="$SCRIPT_DIR"
LOGS_DIR="$DEPLOYMENT_DIR/logs"
CONFIG_DIR="$DEPLOYMENT_DIR/config"

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

log_debug() {
    if [[ "${DEBUG:-false}" == "true" ]]; then
        echo -e "${CYAN}[DEBUG]${NC} $1"
    fi
}

# Global variables
DEPLOYMENT_START_TIME=$(date +%s)
DEPLOYMENT_ID="pa-deploy-$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOGS_DIR/deployment-${DEPLOYMENT_ID}.log"
CONFIG_FILE="$CONFIG_DIR/deploy.conf"
BACKUP_DIR="$DEPLOYMENT_DIR/backups"
ROLLBACK_SCRIPT="$DEPLOYMENT_DIR/scripts/rollback.sh"

# Deployment state
DEPLOYMENT_STATE="initializing"
VALIDATION_PASSED=false
DEPENDENCIES_INSTALLED=false
CONFIGURATION_COMPLETE=false
SERVICES_DEPLOYED=false
HEALTH_CHECKS_PASSED=false

# Create necessary directories
create_directories() {
    log_info "Creating deployment directories..."
    mkdir -p "$LOGS_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$DEPLOYMENT_DIR/scripts"
}

# Initialize logging
init_logging() {
    log_info "Initializing deployment logging..."
    echo "=== PA Ecosystem Deployment Log ===" > "$LOG_FILE"
    echo "Deployment ID: $DEPLOYMENT_ID" >> "$LOG_FILE"
    echo "Start Time: $(date)" >> "$LOG_FILE"
    echo "Host: $(hostname)" >> "$LOG_FILE"
    echo "User: $(whoami)" >> "$LOG_FILE"
    echo "OS: $(uname -a)" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
}

# Log message to both console and file
log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Log to console
    case "$level" in
        "INFO") log_info "$message" ;;
        "SUCCESS") log_success "$message" ;;
        "WARNING") log_warning "$message" ;;
        "ERROR") log_error "$message" ;;
        "STEP") log_step "$message" ;;
        "DEBUG") log_debug "$message" ;;
    esac
    
    # Log to file
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

# Display banner
show_banner() {
    echo -e "${CYAN}"
    echo "=========================================="
    echo "  PA Ecosystem Deployment Script"
    echo "=========================================="
    echo -e "${NC}"
    echo "This script will deploy the complete Personal Assistant ecosystem"
    echo "including all services, databases, and configurations."
    echo ""
}

# Display help information
show_help() {
    echo "PA Ecosystem Deployment Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -v, --verbose           Enable verbose output"
    echo "  -d, --dry-run           Show what would be done without making changes"
    echo "  -c, --config FILE       Use custom configuration file"
    echo "  -f, --force             Force deployment even if validation fails"
    echo "  -q, --quick             Use quick deployment mode (minimal prompts)"
    echo "  --non-interactive       Run in non-interactive mode"
    echo "  --skip-validation       Skip system requirements validation"
    echo "  --skip-dependencies     Skip dependency installation"
    echo "  --backup-only           Only create backup of existing configuration"
    echo "  --restore FILE          Restore from backup file"
    echo ""
    echo "Examples:"
    echo "  $0                      # Interactive deployment"
    echo "  $0 --quick             # Quick deployment with minimal prompts"
    echo "  $0 --dry-run           # Show what would be deployed"
    echo "  $0 --non-interactive   # Automated deployment"
    echo ""
}

# Parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--verbose)
                DEBUG=true
                shift
                ;;
            -d|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -c|--config)
                CONFIG_FILE="$2"
                shift 2
                ;;
            -f|--force)
                FORCE_DEPLOYMENT=true
                shift
                ;;
            -q|--quick)
                QUICK_MODE=true
                shift
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                shift
                ;;
            --skip-validation)
                SKIP_VALIDATION=true
                shift
                ;;
            --skip-dependencies)
                SKIP_DEPENDENCIES=true
                shift
                ;;
            --backup-only)
                BACKUP_ONLY=true
                shift
                ;;
            --restore)
                RESTORE_FROM="$2"
                shift 2
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_warning "Running as root. This is not recommended for security reasons."
        if [[ "${NON_INTERACTIVE:-false}" != "true" ]]; then
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "Deployment cancelled by user"
                exit 0
            fi
        fi
    fi
}

# Validate system requirements
validate_requirements() {
    if [[ "${SKIP_VALIDATION:-false}" == "true" ]]; then
        log_warning "Skipping system requirements validation"
        return 0
    fi
    
    log_step "Validating system requirements..."
    
    if [[ ! -f "$DEPLOYMENT_DIR/scripts/validate-requirements.sh" ]]; then
        log_error "Requirements validation script not found"
        return 1
    fi
    
    if "$DEPLOYMENT_DIR/scripts/validate-requirements.sh"; then
        VALIDATION_PASSED=true
        log_success "System requirements validation passed"
        return 0
    else
        if [[ "${FORCE_DEPLOYMENT:-false}" == "true" ]]; then
            log_warning "Validation failed but continuing due to --force flag"
            VALIDATION_PASSED=false
            return 0
        else
            log_error "System requirements validation failed"
            log_info "Run with --force to continue anyway, or fix the issues and try again"
            return 1
        fi
    fi
}

# Install dependencies
install_dependencies() {
    if [[ "${SKIP_DEPENDENCIES:-false}" == "true" ]]; then
        log_warning "Skipping dependency installation"
        return 0
    fi
    
    log_step "Installing dependencies..."
    
    # Check if Docker is installed
    if ! command -v docker >/dev/null 2>&1; then
        log_info "Installing Docker..."
        if [[ "${DRY_RUN:-false}" == "true" ]]; then
            log_info "DRY RUN: Would install Docker"
        else
            # Install Docker based on OS
            if [[ -f /etc/os-release ]]; then
                . /etc/os-release
                case "$ID" in
                    ubuntu|debian)
                        install_docker_ubuntu
                        ;;
                    centos|rhel|fedora)
                        install_docker_centos
                        ;;
                    *)
                        log_error "Unsupported OS for automatic Docker installation: $ID"
                        return 1
                        ;;
                esac
            else
                log_error "Cannot determine OS for Docker installation"
                return 1
            fi
        fi
    else
        log_success "Docker is already installed"
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
        log_info "Installing Docker Compose..."
        if [[ "${DRY_RUN:-false}" == "true" ]]; then
            log_info "DRY RUN: Would install Docker Compose"
        else
            install_docker_compose
        fi
    else
        log_success "Docker Compose is already installed"
    fi
    
    DEPENDENCIES_INSTALLED=true
    log_success "Dependencies installation completed"
}

# Install Docker on Ubuntu/Debian
install_docker_ubuntu() {
    log_info "Installing Docker on Ubuntu/Debian..."
    
    # Update package index
    sudo apt-get update
    
    # Install required packages
    sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
    
    # Add Docker's official GPG key
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    
    # Set up stable repository
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Update package index again
    sudo apt-get update
    
    # Install Docker Engine
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    
    log_success "Docker installed successfully"
    log_warning "Please log out and log back in for group changes to take effect"
}

# Install Docker on CentOS/RHEL
install_docker_centos() {
    log_info "Installing Docker on CentOS/RHEL..."
    
    # Install required packages
    sudo yum install -y yum-utils
    
    # Add Docker repository
    sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    
    # Install Docker Engine
    sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # Start and enable Docker
    sudo systemctl start docker
    sudo systemctl enable docker
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    
    log_success "Docker installed successfully"
    log_warning "Please log out and log back in for group changes to take effect"
}

# Install Docker Compose
install_docker_compose() {
    log_info "Installing Docker Compose..."
    
    # Get latest version
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    
    # Download and install
    sudo curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    
    log_success "Docker Compose installed successfully"
}

# Interactive configuration wizard
run_configuration_wizard() {
    if [[ "${NON_INTERACTIVE:-false}" == "true" ]]; then
        log_info "Non-interactive mode: using default configuration"
        load_default_configuration
        return 0
    fi
    
    log_step "Running configuration wizard..."
    
    echo ""
    echo "Please provide the following configuration details:"
    echo ""
    
    # Database configuration
    echo "=== Database Configuration ==="
    read -p "PostgreSQL Password (default: pa_secure_password): " POSTGRES_PASSWORD
    POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-pa_secure_password}
    
    read -p "Supabase Anon Key (required): " SUPABASE_ANON_KEY
    if [[ -z "$SUPABASE_ANON_KEY" ]]; then
        log_error "Supabase Anon Key is required"
        return 1
    fi
    
    read -p "Supabase Service Key (required): " SUPABASE_SERVICE_KEY
    if [[ -z "$SUPABASE_SERVICE_KEY" ]]; then
        log_error "Supabase Service Key is required"
        return 1
    fi
    
    # n8n configuration
    echo ""
    echo "=== n8n Configuration ==="
    read -p "n8n Encryption Key (default: auto-generated): " N8N_ENCRYPTION_KEY
    if [[ -z "$N8N_ENCRYPTION_KEY" ]]; then
        N8N_ENCRYPTION_KEY=$(openssl rand -base64 32)
        log_info "Generated n8n encryption key"
    fi
    
    read -p "n8n Webhook URL (required): " N8N_WEBHOOK_URL
    if [[ -z "$N8N_WEBHOOK_URL" ]]; then
        log_error "n8n Webhook URL is required"
        return 1
    fi
    
    read -p "General Webhook URL (default: same as n8n): " WEBHOOK_URL
    WEBHOOK_URL=${WEBHOOK_URL:-$N8N_WEBHOOK_URL}
    
    # API Keys
    echo ""
    echo "=== API Keys ==="
    read -p "OpenAI API Key (required): " OPENAI_API_KEY
    if [[ -z "$OPENAI_API_KEY" ]]; then
        log_error "OpenAI API Key is required"
        return 1
    fi
    
    read -p "Anthropic API Key (required): " ANTHROPIC_API_KEY
    if [[ -z "$ANTHROPIC_API_KEY" ]]; then
        log_error "Anthropic API Key is required"
        return 1
    fi
    
    read -p "Google Gemini API Key (required): " GEMINI_API_KEY
    if [[ -z "$GEMINI_API_KEY" ]]; then
        log_error "Google Gemini API Key is required"
        return 1
    fi
    
    # Slack configuration
    echo ""
    echo "=== Slack Configuration ==="
    read -p "Slack Bot Token (required): " SLACK_BOT_TOKEN
    if [[ -z "$SLACK_BOT_TOKEN" ]]; then
        log_error "Slack Bot Token is required"
        return 1
    fi
    
    read -p "Slack App Token (required): " SLACK_APP_TOKEN
    if [[ -z "$SLACK_APP_TOKEN" ]]; then
        log_error "Slack App Token is required"
        return 1
    fi
    
    read -p "Letta Agent ID (required): " LETTA_AGENT_ID
    if [[ -z "$LETTA_AGENT_ID" ]]; then
        log_error "Letta Agent ID is required"
        return 1
    fi
    
    # Cloudflare configuration
    echo ""
    echo "=== Cloudflare Configuration ==="
    read -p "Cloudflare Tunnel Token (optional): " CLOUDFLARE_TUNNEL_TOKEN
    if [[ -z "$CLOUDFLARE_TUNNEL_TOKEN" ]]; then
        log_warning "Cloudflare Tunnel Token not provided - external access will not be available"
    fi
    
    # Save configuration
    save_configuration
    
    CONFIGURATION_COMPLETE=true
    log_success "Configuration completed"
}

# Load default configuration
load_default_configuration() {
    log_info "Loading default configuration..."
    
    # Set default values
    POSTGRES_PASSWORD="pa_secure_password"
    N8N_ENCRYPTION_KEY=$(openssl rand -base64 32)
    WEBHOOK_URL="http://localhost:5678"
    
    # Check if .env file exists
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        log_info "Loading existing .env file"
        source "$PROJECT_ROOT/.env"
    else
        log_warning "No .env file found - using defaults"
    fi
    
    CONFIGURATION_COMPLETE=true
}

# Save configuration to file
save_configuration() {
    log_info "Saving configuration..."
    
    local env_file="$PROJECT_ROOT/.env"
    
    cat > "$env_file" << EOF
# PA Ecosystem Environment Configuration
# Generated by deployment script on $(date)

# Database Configuration
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
SUPABASE_ANON_KEY=$SUPABASE_ANON_KEY
SUPABASE_SERVICE_KEY=$SUPABASE_SERVICE_KEY

# n8n Configuration
N8N_ENCRYPTION_KEY=$N8N_ENCRYPTION_KEY
N8N_WEBHOOK_URL=$N8N_WEBHOOK_URL
WEBHOOK_URL=$WEBHOOK_URL

# API Keys
OPENAI_API_KEY=$OPENAI_API_KEY
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
GEMINI_API_KEY=$GEMINI_API_KEY

# Slack Configuration
SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN
SLACK_APP_TOKEN=$SLACK_APP_TOKEN
LETTA_AGENT_ID=$LETTA_AGENT_ID

# Cloudflare Configuration
CLOUDFLARE_TUNNEL_TOKEN=$CLOUDFLARE_TUNNEL_TOKEN

# Optional Configuration
LETTA_DEBUG=false
OPENWEBUI_LOG_LEVEL=INFO
ENABLE_TAGS_GENERATION=true
ENABLE_TITLE_GENERATION=true
TASK_MODEL=gpt-4
TASK_MODEL_EXTERNAL=gpt-4
ENABLE_OLLAMA_API=false
OLLAMA_BASE_URL=http://localhost:11434
RAG_EMBEDDING_ENGINE=openai
RAG_EMBEDDING_MODEL=text-embedding-ada-002
LITELLM_MASTER_KEY=$(openssl rand -base64 32)
ENABLE_WEB_SEARCH=false
WEB_SEARCH_ENGINE=tavily
TAVILY_API_KEY=
AUDIO_STT_ENGINE=openai
EOF
    
    # Set secure permissions
    chmod 600 "$env_file"
    
    log_success "Configuration saved to $env_file"
}

# Deploy services using Docker Compose
deploy_services() {
    log_step "Deploying services with Docker Compose..."
    
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_info "DRY RUN: Would deploy services with Docker Compose"
        return 0
    fi
    
    # Change to project root directory
    cd "$PROJECT_ROOT"
    
    # Check if docker-compose.yml exists
    if [[ ! -f "docker-compose.yml" ]]; then
        log_error "docker-compose.yml not found in project root"
        return 1
    fi
    
    # Create Docker network if it doesn't exist
    if ! docker network ls | grep -q "pa-internal"; then
        log_info "Creating Docker network: pa-internal"
        docker network create pa-internal
    fi
    
    # Start services
    log_info "Starting services..."
    if docker-compose up -d; then
        SERVICES_DEPLOYED=true
        log_success "Services deployed successfully"
    else
        log_error "Failed to deploy services"
        return 1
    fi
}

# Run health checks
run_health_checks() {
    log_step "Running health checks..."
    
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_info "DRY RUN: Would run health checks"
        return 0
    fi
    
    # Wait for services to start
    log_info "Waiting for services to start..."
    sleep 30
    
    # Check service health
    local services=("supabase-db" "n8n" "letta" "open-webui" "slackbot")
    local all_healthy=true
    
    for service in "${services[@]}"; do
        if docker-compose ps "$service" | grep -q "Up"; then
            log_success "Service $service is running"
        else
            log_error "Service $service is not running"
            all_healthy=false
        fi
    done
    
    if [[ "$all_healthy" == "true" ]]; then
        HEALTH_CHECKS_PASSED=true
        log_success "All health checks passed"
    else
        log_error "Some health checks failed"
        return 1
    fi
}

# Display deployment summary
show_deployment_summary() {
    local end_time=$(date +%s)
    local duration=$((end_time - DEPLOYMENT_START_TIME))
    
    echo ""
    echo -e "${GREEN}=========================================="
    echo "  Deployment Summary"
    echo "==========================================${NC}"
    echo ""
    echo "Deployment ID: $DEPLOYMENT_ID"
    echo "Duration: ${duration} seconds"
    echo "Status: $([ "$HEALTH_CHECKS_PASSED" == "true" ] && echo "SUCCESS" || echo "FAILED")"
    echo ""
    echo "Services deployed:"
    echo "  - PostgreSQL Database (Supabase)"
    echo "  - n8n Workflow Automation"
    echo "  - Letta AI Agent"
    echo "  - Open WebUI Interface"
    echo "  - Slackbot Integration"
    echo "  - Health Monitor"
    echo ""
    echo "Access URLs:"
    echo "  - Letta Web Interface: http://localhost:8283"
    echo "  - Open WebUI: http://localhost:8080"
    echo "  - n8n Interface: http://localhost:5678"
    echo "  - Health Monitor: http://localhost:8083"
    echo ""
    echo "Configuration file: $PROJECT_ROOT/.env"
    echo "Deployment log: $LOG_FILE"
    echo ""
    
    if [[ "$HEALTH_CHECKS_PASSED" == "true" ]]; then
        log_success "Deployment completed successfully!"
        echo ""
        echo "Next steps:"
        echo "1. Access the web interfaces using the URLs above"
        echo "2. Configure your Slack bot using the provided tokens"
        echo "3. Set up Cloudflare tunnel for external access (optional)"
        echo "4. Review the deployment log for any warnings"
    else
        log_error "Deployment completed with errors"
        echo ""
        echo "Troubleshooting:"
        echo "1. Check the deployment log: $LOG_FILE"
        echo "2. Verify all required environment variables are set"
        echo "3. Ensure all required ports are available"
        echo "4. Check Docker and Docker Compose are running properly"
    fi
}

# Cleanup function
cleanup() {
    local exit_code=$?
    
    if [[ $exit_code -ne 0 ]]; then
        log_error "Deployment failed with exit code $exit_code"
        
        if [[ -f "$ROLLBACK_SCRIPT" ]]; then
            log_info "Running rollback script..."
            "$ROLLBACK_SCRIPT" "$DEPLOYMENT_ID"
        fi
    fi
    
    # Log deployment end
    echo "End Time: $(date)" >> "$LOG_FILE"
    echo "Exit Code: $exit_code" >> "$LOG_FILE"
    
    exit $exit_code
}

# Set up signal handlers
trap cleanup EXIT INT TERM

# Main deployment function
main() {
    # Initialize
    create_directories
    init_logging
    show_banner
    parse_arguments "$@"
    check_root
    
    # Set deployment state
    DEPLOYMENT_STATE="validating"
    
    # Validate requirements
    if ! validate_requirements; then
        log_error "Requirements validation failed"
        exit 1
    fi
    
    # Set deployment state
    DEPLOYMENT_STATE="installing"
    
    # Install dependencies
    if ! install_dependencies; then
        log_error "Dependency installation failed"
        exit 1
    fi
    
    # Set deployment state
    DEPLOYMENT_STATE="configuring"
    
    # Run configuration wizard
    if ! run_configuration_wizard; then
        log_error "Configuration failed"
        exit 1
    fi
    
    # Set deployment state
    DEPLOYMENT_STATE="deploying"
    
    # Deploy services
    if ! deploy_services; then
        log_error "Service deployment failed"
        exit 1
    fi
    
    # Set deployment state
    DEPLOYMENT_STATE="validating"
    
    # Run health checks
    if ! run_health_checks; then
        log_error "Health checks failed"
        exit 1
    fi
    
    # Set deployment state
    DEPLOYMENT_STATE="completed"
    
    # Show summary
    show_deployment_summary
}

# Run main function
main "$@"
