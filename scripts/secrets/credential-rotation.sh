#!/bin/bash

# PA Ecosystem Credential Rotation Script
# Automated credential rotation for critical services
# Created: 2025-01-21

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
SECRETS_MANAGER="$SCRIPT_DIR/secrets-manager.sh"
LOG_FILE="$PROJECT_ROOT/logs/credential-rotation.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log messages
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "$LOG_FILE"
}

# Function to check prerequisites
check_prerequisites() {
    log "Checking credential rotation prerequisites..."
    
    # Check if secrets manager exists
    if [ ! -f "$SECRETS_MANAGER" ]; then
        error "Secrets manager not found: $SECRETS_MANAGER"
        exit 1
    fi
    
    # Check if secrets manager is executable
    if [ ! -x "$SECRETS_MANAGER" ]; then
        error "Secrets manager is not executable"
        exit 1
    fi
    
    # Create log directory
    mkdir -p "$(dirname "$LOG_FILE")"
    
    log "✓ Prerequisites check passed"
}

# Function to check if credential needs rotation
check_rotation_needed() {
    local secret_name="$1"
    
    # Get secret expiration date
    local expires_date=$(jq -r --arg name "$secret_name" '.secrets[$name].expires // empty' "$PROJECT_ROOT/config/secrets/inventory.json")
    
    if [ -z "$expires_date" ] || [ "$expires_date" = "null" ]; then
        return 1  # No expiration date set
    fi
    
    # Check if expired or expiring within 7 days
    local current_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local warning_time=$(date -u -d "+7 days" +%Y-%m-%dT%H:%M:%SZ)
    
    if [ "$current_time" \> "$expires_date" ]; then
        return 0  # Expired
    elif [ "$warning_time" \> "$expires_date" ]; then
        return 0  # Expiring soon
    fi
    
    return 1  # Not needed
}

# Function to rotate database password
rotate_database_password() {
    local secret_name="$1"
    local service_name="$2"
    
    log "Rotating database password for $service_name..."
    
    # Generate new password
    local new_password=$("$SECRETS_MANAGER" generate-secret password 32)
    
    # Store new password
    "$SECRETS_MANAGER" store "$secret_name" "$new_password" password 90
    
    # Update service configuration if running
    if docker ps | grep -q "$service_name"; then
        info "Updating $service_name configuration..."
        
        # Update environment variable in running container
        docker exec "$service_name" bash -c "export ${secret_name^^}=$new_password"
        
        # Restart service to pick up new password
        docker restart "$service_name"
        
        log "✓ $service_name restarted with new password"
    else
        warning "$service_name is not running - password updated but service needs to be restarted"
    fi
    
    log "✓ Database password rotated for $service_name"
}

# Function to rotate API key
rotate_api_key() {
    local secret_name="$1"
    local service_name="$2"
    
    log "Rotating API key for $service_name..."
    
    warning "API key rotation requires manual intervention"
    info "Please update the API key in the external service dashboard"
    info "Then run: $SECRETS_MANAGER store $secret_name 'new-api-key'"
    
    # Mark for manual rotation
    echo "$(date): Manual API key rotation required for $secret_name" >> "$LOG_FILE"
}

# Function to rotate encryption key
rotate_encryption_key() {
    local secret_name="$1"
    local service_name="$2"
    
    log "Rotating encryption key for $service_name..."
    
    # Generate new encryption key
    local new_key=$("$SECRETS_MANAGER" generate-secret key 32)
    
    # Store new key
    "$SECRETS_MANAGER" store "$secret_name" "$new_key" key 90
    
    # Update service configuration if running
    if docker ps | grep -q "$service_name"; then
        info "Updating $service_name encryption key..."
        
        # Update environment variable in running container
        docker exec "$service_name" bash -c "export ${secret_name^^}=$new_key"
        
        # Restart service to pick up new key
        docker restart "$service_name"
        
        log "✓ $service_name restarted with new encryption key"
    else
        warning "$service_name is not running - key updated but service needs to be restarted"
    fi
    
    log "✓ Encryption key rotated for $service_name"
}

# Function to rotate all credentials
rotate_all_credentials() {
    log "Starting automated credential rotation..."
    
    # Define credentials that need rotation
    local credentials=(
        "postgres-password:postgres:database"
        "n8n-encryption-key:n8n:encryption"
        "litellm-master-key:openwebui:encryption"
        "jwt-secret:letta:encryption"
        "data-encryption-key:global:encryption"
    )
    
    local rotated_count=0
    local skipped_count=0
    
    for credential in "${credentials[@]}"; do
        IFS=':' read -r secret_name service_name credential_type <<< "$credential"
        
        if check_rotation_needed "$secret_name"; then
            case "$credential_type" in
                "database")
                    rotate_database_password "$secret_name" "$service_name"
                    ;;
                "encryption")
                    rotate_encryption_key "$secret_name" "$service_name"
                    ;;
                "api")
                    rotate_api_key "$secret_name" "$service_name"
                    ;;
                *)
                    warning "Unknown credential type: $credential_type"
                    ;;
            esac
            ((rotated_count++))
        else
            info "Skipping $secret_name - rotation not needed"
            ((skipped_count++))
        fi
    done
    
    log "Credential rotation completed: $rotated_count rotated, $skipped_count skipped"
}

# Function to check rotation schedule
check_rotation_schedule() {
    log "Checking credential rotation schedule..."
    
    # Check for expired credentials
    local expired_secrets=()
    
    while IFS= read -r secret_name; do
        if check_rotation_needed "$secret_name"; then
            expired_secrets+=("$secret_name")
        fi
    done < <(jq -r '.secrets | keys[]' "$PROJECT_ROOT/config/secrets/inventory.json" 2>/dev/null || true)
    
    if [ ${#expired_secrets[@]} -eq 0 ]; then
        log "✓ No credentials require rotation at this time"
    else
        warning "Credentials requiring rotation:"
        for secret in "${expired_secrets[@]}"; do
            warning "  - $secret"
        done
    fi
    
    return ${#expired_secrets[@]}
}

# Function to set up rotation schedule
setup_rotation_schedule() {
    log "Setting up automated credential rotation schedule..."
    
    # Create cron job for daily rotation check
    local cron_job="0 2 * * * $SCRIPT_DIR/credential-rotation.sh check-schedule >> $LOG_FILE 2>&1"
    
    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -q "credential-rotation.sh"; then
        info "Rotation schedule already configured"
    else
        # Add cron job
        (crontab -l 2>/dev/null; echo "$cron_job") | crontab -
        log "✓ Daily rotation check scheduled at 2:00 AM"
    fi
    
    # Create weekly full rotation job
    local weekly_cron_job="0 3 * * 0 $SCRIPT_DIR/credential-rotation.sh rotate-all >> $LOG_FILE 2>&1"
    
    if crontab -l 2>/dev/null | grep -q "rotate-all"; then
        info "Weekly rotation already configured"
    else
        (crontab -l 2>/dev/null; echo "$weekly_cron_job") | crontab -
        log "✓ Weekly full rotation scheduled for Sundays at 3:00 AM"
    fi
}

# Function to show rotation status
show_rotation_status() {
    log "Credential Rotation Status"
    log "========================="
    
    if [ ! -f "$PROJECT_ROOT/config/secrets/inventory.json" ]; then
        error "No secrets inventory found. Run 'secrets-manager.sh initialize' first."
        return 1
    fi
    
    # Show all credentials with expiration dates
    while IFS= read -r secret_name; do
        local expires=$(jq -r --arg name "$secret_name" '.secrets[$name].expires // "Never"' "$PROJECT_ROOT/config/secrets/inventory.json")
        local created=$(jq -r --arg name "$secret_name" '.secrets[$name].created // "Unknown"' "$PROJECT_ROOT/config/secrets/inventory.json")
        local type=$(jq -r --arg name "$secret_name" '.secrets[$name].type // "Unknown"' "$PROJECT_ROOT/config/secrets/inventory.json")
        
        if check_rotation_needed "$secret_name"; then
            echo -e "  ${RED}⚠️  $secret_name ($type) - Expires: $expires${NC}"
        else
            echo -e "  ${GREEN}✓ $secret_name ($type) - Expires: $expires${NC}"
        fi
    done < <(jq -r '.secrets | keys[]' "$PROJECT_ROOT/config/secrets/inventory.json")
    
    echo ""
    
    # Show rotation schedule
    info "Rotation Schedule:"
    crontab -l 2>/dev/null | grep "credential-rotation.sh" || echo "  No rotation schedule configured"
}

# Function to show help
show_help() {
    echo "PA Ecosystem Credential Rotation Script"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  check-schedule              Check which credentials need rotation"
    echo "  rotate-all                 Rotate all credentials that need rotation"
    echo "  rotate NAME SERVICE TYPE   Rotate specific credential"
    echo "  setup-schedule             Set up automated rotation schedule"
    echo "  status                     Show rotation status for all credentials"
    echo "  help                       Show this help message"
    echo ""
    echo "Credential Types:"
    echo "  database                   Database passwords"
    echo "  encryption                 Encryption keys"
    echo "  api                        API keys (manual rotation required)"
    echo ""
    echo "Examples:"
    echo "  $0 check-schedule          # Check what needs rotation"
    echo "  $0 rotate-all              # Rotate all credentials"
    echo "  $0 rotate postgres-password postgres database"
    echo "  $0 setup-schedule          # Set up automated rotation"
    echo "  $0 status                  # Show status"
}

# Main function
main() {
    local command="$1"
    shift
    
    log "Credential Rotation Script - $(date)"
    log "===================================="
    
    # Check prerequisites
    check_prerequisites
    
    # Execute command
    case "$command" in
        "check-schedule")
            check_rotation_schedule
            ;;
        "rotate-all")
            rotate_all_credentials
            ;;
        "rotate")
            local secret_name="$1"
            local service_name="$2"
            local credential_type="$3"
            
            if [ -z "$secret_name" ] || [ -z "$service_name" ] || [ -z "$credential_type" ]; then
                error "Usage: rotate NAME SERVICE TYPE"
                exit 1
            fi
            
            case "$credential_type" in
                "database")
                    rotate_database_password "$secret_name" "$service_name"
                    ;;
                "encryption")
                    rotate_encryption_key "$secret_name" "$service_name"
                    ;;
                "api")
                    rotate_api_key "$secret_name" "$service_name"
                    ;;
                *)
                    error "Unknown credential type: $credential_type"
                    exit 1
                    ;;
            esac
            ;;
        "setup-schedule")
            setup_rotation_schedule
            ;;
        "status")
            show_rotation_status
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
    
    log "Credential rotation operation completed"
}

# Run main function
main "$@"
