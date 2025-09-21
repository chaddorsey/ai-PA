#!/bin/bash

# PA Ecosystem Configuration Validation Script
# This script validates the .env configuration file

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$DEPLOYMENT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

# Color codes for output
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

# Validation results
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Check if .env file exists
check_env_file() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if [[ -f "$ENV_FILE" ]]; then
        log_success ".env file exists"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        log_error ".env file not found at $ENV_FILE"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

# Load environment variables
load_env() {
    if [[ -f "$ENV_FILE" ]]; then
        # Export variables from .env file
        set -a
        source "$ENV_FILE"
        set +a
        log_info "Environment variables loaded"
    else
        log_error "Cannot load environment variables - .env file not found"
        return 1
    fi
}

# Check required variables
check_required_variables() {
    local required_vars=(
        "POSTGRES_PASSWORD"
        "SUPABASE_ANON_KEY"
        "SUPABASE_SERVICE_KEY"
        "N8N_ENCRYPTION_KEY"
        "OPENAI_API_KEY"
    )
    
    for var in "${required_vars[@]}"; do
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
        
        if [[ -n "${!var:-}" ]]; then
            log_success "Required variable $var is set"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_error "Required variable $var is not set"
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
        fi
    done
}

# Check API key formats
check_api_key_formats() {
    # Check OpenAI API key format
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    if [[ -n "${OPENAI_API_KEY:-}" ]]; then
        if [[ "$OPENAI_API_KEY" =~ ^sk- ]]; then
            log_success "OpenAI API key format is valid"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_warning "OpenAI API key format may be invalid (should start with 'sk-')"
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    fi
    
    # Check Anthropic API key format
    if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
        if [[ "$ANTHROPIC_API_KEY" =~ ^sk-ant- ]]; then
            log_success "Anthropic API key format is valid"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_warning "Anthropic API key format may be invalid (should start with 'sk-ant-')"
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    fi
    
    # Check Gemini API key format
    if [[ -n "${GEMINI_API_KEY:-}" ]]; then
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
        if [[ "$GEMINI_API_KEY" =~ ^AIzaSy ]]; then
            log_success "Gemini API key format is valid"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_warning "Gemini API key format may be invalid (should start with 'AIzaSy')"
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    fi
}

# Check password strength
check_password_strength() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if [[ -n "${POSTGRES_PASSWORD:-}" ]]; then
        local password_length=${#POSTGRES_PASSWORD}
        if [[ $password_length -ge 32 ]]; then
            log_success "PostgreSQL password is sufficiently long ($password_length characters)"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_warning "PostgreSQL password is too short ($password_length characters, minimum 32 recommended)"
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    else
        log_error "PostgreSQL password is not set"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
}

# Check encryption key strength
check_encryption_key() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if [[ -n "${N8N_ENCRYPTION_KEY:-}" ]]; then
        local key_length=${#N8N_ENCRYPTION_KEY}
        if [[ $key_length -ge 32 ]]; then
            log_success "N8N encryption key is sufficiently long ($key_length characters)"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_warning "N8N encryption key is too short ($key_length characters, minimum 32 recommended)"
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    else
        log_error "N8N encryption key is not set"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
}

# Check URL formats
check_url_formats() {
    # Check N8N webhook URL
    if [[ -n "${N8N_WEBHOOK_URL:-}" ]]; then
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
        if [[ "$N8N_WEBHOOK_URL" =~ ^https?:// ]]; then
            log_success "N8N webhook URL format is valid"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_warning "N8N webhook URL format may be invalid (should start with http:// or https://)"
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    fi
    
    # Check webhook URL
    if [[ -n "${WEBHOOK_URL:-}" ]]; then
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
        if [[ "$WEBHOOK_URL" =~ ^https?:// ]]; then
            log_success "Webhook URL format is valid"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_warning "Webhook URL format may be invalid (should start with http:// or https://)"
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    fi
}

# Check Slack configuration
check_slack_config() {
    local slack_vars=("SLACK_BOT_TOKEN" "SLACK_APP_TOKEN")
    local slack_configured=true
    
    for var in "${slack_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            slack_configured=false
            break
        fi
    done
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if [[ "$slack_configured" == "true" ]]; then
        log_success "Slack configuration is complete"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        log_warning "Slack configuration is incomplete (optional for local development)"
        WARNING_CHECKS=$((WARNING_CHECKS + 1))
    fi
}

# Check Cloudflare configuration
check_cloudflare_config() {
    local cloudflare_vars=("CLOUDFLARE_TUNNEL_TOKEN" "CLOUDFLARE_ACCOUNT_ID" "CLOUDFLARE_ZONE_ID" "CLOUDFLARE_API_TOKEN")
    local cloudflare_configured=true
    
    for var in "${cloudflare_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            cloudflare_configured=false
            break
        fi
    done
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if [[ "$cloudflare_configured" == "true" ]]; then
        log_success "Cloudflare configuration is complete"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        log_warning "Cloudflare configuration is incomplete (optional for local development)"
        WARNING_CHECKS=$((WARNING_CHECKS + 1))
    fi
}

# Check for placeholder values
check_placeholder_values() {
    local placeholder_vars=()
    
    # Check for common placeholder patterns
    while IFS= read -r line; do
        if [[ "$line" =~ ^[A-Z_]+=.*CHANGE_ME.* ]]; then
            local var_name=$(echo "$line" | cut -d'=' -f1)
            placeholder_vars+=("$var_name")
        fi
    done < "$ENV_FILE"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if [[ ${#placeholder_vars[@]} -eq 0 ]]; then
        log_success "No placeholder values found"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        log_warning "Found ${#placeholder_vars[@]} placeholder values that need to be replaced:"
        for var in "${placeholder_vars[@]}"; do
            echo "  - $var"
        done
        WARNING_CHECKS=$((WARNING_CHECKS + 1))
    fi
}

# Check model configurations
check_model_configs() {
    # Check Letta chat model
    if [[ -n "${LETTA_CHAT_MODEL:-}" ]]; then
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
        if [[ "$LETTA_CHAT_MODEL" =~ ^(openai|anthropic|google_ai|letta)/ ]]; then
            log_success "Letta chat model format is valid: $LETTA_CHAT_MODEL"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_warning "Letta chat model format may be invalid: $LETTA_CHAT_MODEL"
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    fi
    
    # Check embedding model
    if [[ -n "${LETTA_EMBEDDING_MODEL:-}" ]]; then
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
        if [[ "$LETTA_EMBEDDING_MODEL" =~ ^(openai|anthropic|google_ai|letta)/ ]]; then
            log_success "Letta embedding model format is valid: $LETTA_EMBEDDING_MODEL"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_warning "Letta embedding model format may be invalid: $LETTA_EMBEDDING_MODEL"
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    fi
}

# Display validation summary
show_validation_summary() {
    echo ""
    echo -e "${BLUE}=========================================="
    echo "  Configuration Validation Summary"
    echo "==========================================${NC}"
    echo ""
    echo "Total checks: $TOTAL_CHECKS"
    echo -e "Passed: ${GREEN}$PASSED_CHECKS${NC}"
    echo -e "Failed: ${RED}$FAILED_CHECKS${NC}"
    echo -e "Warnings: ${YELLOW}$WARNING_CHECKS${NC}"
    echo ""
    
    if [[ $FAILED_CHECKS -eq 0 ]]; then
        if [[ $WARNING_CHECKS -eq 0 ]]; then
            log_success "Configuration validation passed!"
            echo ""
            echo "Your configuration is ready for deployment."
        else
            log_warning "Configuration validation passed with warnings"
            echo ""
            echo "Your configuration is ready for deployment, but consider addressing the warnings above."
        fi
    else
        log_error "Configuration validation failed"
        echo ""
        echo "Please fix the errors above before deploying."
        echo "Run this script again after making changes."
    fi
}

# Main validation function
main() {
    echo -e "${BLUE}=========================================="
    echo "  PA Ecosystem Configuration Validation"
    echo "==========================================${NC}"
    echo ""
    
    # Check if .env file exists
    if ! check_env_file; then
        echo ""
        echo "To create a configuration file:"
        echo "1. Run: ./deployment/scripts/select-template.sh"
        echo "2. Or copy a template: cp deployment/templates/development.env .env"
        echo "3. Edit the .env file with your configuration"
        exit 1
    fi
    
    # Load environment variables
    load_env
    
    # Run validation checks
    check_required_variables
    check_api_key_formats
    check_password_strength
    check_encryption_key
    check_url_formats
    check_slack_config
    check_cloudflare_config
    check_placeholder_values
    check_model_configs
    
    # Show summary
    show_validation_summary
    
    # Exit with appropriate code
    if [[ $FAILED_CHECKS -eq 0 ]]; then
        exit 0
    else
        exit 1
    fi
}

# Run main function
main "$@"
