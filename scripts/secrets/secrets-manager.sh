#!/bin/bash

# PA Ecosystem Secrets Management Framework
# Comprehensive secrets management with encryption, rotation, and audit capabilities
# Created: 2025-01-21

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
SECRETS_DIR="$PROJECT_ROOT/config/secrets"
BACKUP_DIR="$PROJECT_ROOT/backups/secrets"
LOG_FILE="$PROJECT_ROOT/logs/secrets-manager.log"

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
    log "Checking secrets management prerequisites..."
    
    # Check if required tools are available
    local required_tools=("openssl" "gpg" "jq" "base64")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            error "Required tool '$tool' is not installed"
            exit 1
        fi
    done
    
    # Create necessary directories
    mkdir -p "$SECRETS_DIR" "$BACKUP_DIR" "$(dirname "$LOG_FILE")"
    
    # Set secure permissions
    chmod 700 "$SECRETS_DIR"
    chmod 700 "$BACKUP_DIR"
    
    log "✓ Prerequisites check passed"
}

# Function to generate secure random secrets
generate_secret() {
    local secret_type="$1"
    local length="${2:-32}"
    
    case "$secret_type" in
        "password")
            openssl rand -base64 "$length" | tr -d "=+/" | cut -c1-"$length"
            ;;
        "token")
            openssl rand -hex "$length"
            ;;
        "key")
            openssl rand -base64 "$length"
            ;;
        "uuid")
            uuidgen | tr '[:upper:]' '[:lower:]'
            ;;
        *)
            openssl rand -base64 "$length"
            ;;
    esac
}

# Function to encrypt secret
encrypt_secret() {
    local secret="$1"
    local key_file="$2"
    
    if [ ! -f "$key_file" ]; then
        error "Encryption key file not found: $key_file"
        return 1
    fi
    
    echo "$secret" | openssl enc -aes-256-cbc -base64 -pass file:"$key_file"
}

# Function to decrypt secret
decrypt_secret() {
    local encrypted_secret="$1"
    local key_file="$2"
    
    if [ ! -f "$key_file" ]; then
        error "Decryption key file not found: $key_file"
        return 1
    fi
    
    echo "$encrypted_secret" | openssl enc -aes-256-cbc -d -base64 -pass file:"$key_file"
}

# Function to create master encryption key
create_master_key() {
    local key_file="$SECRETS_DIR/master.key"
    
    if [ -f "$key_file" ]; then
        warning "Master key already exists. Use --force to regenerate."
        return 1
    fi
    
    log "Creating master encryption key..."
    openssl rand -base64 32 > "$key_file"
    chmod 600 "$key_file"
    
    log "✓ Master encryption key created: $key_file"
    info "IMPORTANT: Backup this key securely - it cannot be recovered if lost!"
}

# Function to initialize secrets management
initialize_secrets() {
    log "Initializing secrets management framework..."
    
    # Create master key if it doesn't exist
    if [ ! -f "$SECRETS_DIR/master.key" ]; then
        create_master_key
    fi
    
    # Create secrets inventory
    cat > "$SECRETS_DIR/inventory.json" << 'EOF'
{
  "secrets": {},
  "metadata": {
    "created": "",
    "last_updated": "",
    "version": "1.0.0"
  }
}
EOF
    
    # Update metadata
    jq --arg created "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       --arg updated "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       '.metadata.created = $created | .metadata.last_updated = $updated' \
       "$SECRETS_DIR/inventory.json" > "$SECRETS_DIR/inventory.json.tmp" && \
       mv "$SECRETS_DIR/inventory.json.tmp" "$SECRETS_DIR/inventory.json"
    
    log "✓ Secrets management framework initialized"
}

# Function to store secret
store_secret() {
    local secret_name="$1"
    local secret_value="$2"
    local secret_type="${3:-password}"
    local rotation_days="${4:-90}"
    
    if [ -z "$secret_name" ] || [ -z "$secret_value" ]; then
        error "Secret name and value are required"
        return 1
    fi
    
    local key_file="$SECRETS_DIR/master.key"
    if [ ! -f "$key_file" ]; then
        error "Master key not found. Run 'initialize' first."
        return 1
    fi
    
    log "Storing secret: $secret_name"
    
    # Encrypt the secret
    local encrypted_secret=$(encrypt_secret "$secret_value" "$key_file")
    
    # Create secret metadata
    local secret_metadata=$(jq -n \
        --arg name "$secret_name" \
        --arg type "$secret_type" \
        --arg created "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --arg expires "$(date -u -d "+$rotation_days days" +%Y-%m-%dT%H:%M:%SZ)" \
        --arg encrypted "$encrypted_secret" \
        '{
            name: $name,
            type: $type,
            created: $created,
            expires: $expires,
            encrypted: $encrypted,
            rotation_days: '$rotation_days'
        }')
    
    # Update inventory
    jq --arg name "$secret_name" --argjson metadata "$secret_metadata" \
       '.secrets[$name] = $metadata | .metadata.last_updated = now | .metadata.last_updated |= strftime("%Y-%m-%dT%H:%M:%SZ")' \
       "$SECRETS_DIR/inventory.json" > "$SECRETS_DIR/inventory.json.tmp" && \
       mv "$SECRETS_DIR/inventory.json.tmp" "$SECRETS_DIR/inventory.json"
    
    log "✓ Secret '$secret_name' stored successfully"
}

# Function to retrieve secret
retrieve_secret() {
    local secret_name="$1"
    
    if [ -z "$secret_name" ]; then
        error "Secret name is required"
        return 1
    fi
    
    local key_file="$SECRETS_DIR/master.key"
    if [ ! -f "$key_file" ]; then
        error "Master key not found"
        return 1
    fi
    
    # Get encrypted secret from inventory
    local encrypted_secret=$(jq -r --arg name "$secret_name" '.secrets[$name].encrypted // empty' "$SECRETS_DIR/inventory.json")
    
    if [ -z "$encrypted_secret" ] || [ "$encrypted_secret" = "null" ]; then
        error "Secret '$secret_name' not found"
        return 1
    fi
    
    # Decrypt and return secret
    decrypt_secret "$encrypted_secret" "$key_file"
}

# Function to list secrets
list_secrets() {
    log "Available secrets:"
    
    if [ ! -f "$SECRETS_DIR/inventory.json" ]; then
        warning "No secrets inventory found. Run 'initialize' first."
        return 1
    fi
    
    jq -r '.secrets | to_entries[] | "\(.key): \(.value.type) (expires: \(.value.expires))"' "$SECRETS_DIR/inventory.json"
}

# Function to rotate secret
rotate_secret() {
    local secret_name="$1"
    local new_value="$2"
    
    if [ -z "$secret_name" ]; then
        error "Secret name is required"
        return 1
    fi
    
    # Generate new value if not provided
    if [ -z "$new_value" ]; then
        local secret_type=$(jq -r --arg name "$secret_name" '.secrets[$name].type // "password"' "$SECRETS_DIR/inventory.json")
        new_value=$(generate_secret "$secret_type")
        info "Generated new value for '$secret_name'"
    fi
    
    log "Rotating secret: $secret_name"
    
    # Store new secret (this updates the existing entry)
    store_secret "$secret_name" "$new_value"
    
    # Log rotation event
    log "✓ Secret '$secret_name' rotated successfully"
}

# Function to check for expired secrets
check_expired_secrets() {
    log "Checking for expired secrets..."
    
    local current_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local expired_secrets=()
    
    # Check each secret for expiration
    while IFS= read -r line; do
        local secret_name=$(echo "$line" | cut -d':' -f1)
        local expires=$(jq -r --arg name "$secret_name" '.secrets[$name].expires' "$SECRETS_DIR/inventory.json")
        
        if [ "$expires" != "null" ] && [ "$expires" != "" ]; then
            if [ "$current_time" \> "$expires" ]; then
                expired_secrets+=("$secret_name")
            fi
        fi
    done < <(jq -r '.secrets | keys[]' "$SECRETS_DIR/inventory.json")
    
    if [ ${#expired_secrets[@]} -eq 0 ]; then
        log "✓ No expired secrets found"
    else
        warning "Expired secrets found:"
        for secret in "${expired_secrets[@]}"; do
            warning "  - $secret"
        done
    fi
    
    return ${#expired_secrets[@]}
}

# Function to backup secrets
backup_secrets() {
    log "Creating secrets backup..."
    
    local backup_timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="$BACKUP_DIR/secrets-backup-$backup_timestamp"
    
    mkdir -p "$backup_path"
    
    # Copy secrets directory
    cp -r "$SECRETS_DIR" "$backup_path/"
    
    # Create backup manifest
    cat > "$backup_path/manifest.json" << EOF
{
  "backup_type": "secrets",
  "timestamp": "$backup_timestamp",
  "backup_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "secrets_count": $(jq '.secrets | length' "$SECRETS_DIR/inventory.json"),
  "backup_path": "$backup_path"
}
EOF
    
    # Compress backup
    tar -czf "$backup_path.tar.gz" -C "$BACKUP_DIR" "secrets-backup-$backup_timestamp"
    rm -rf "$backup_path"
    
    log "✓ Secrets backup created: $backup_path.tar.gz"
}

# Function to restore secrets
restore_secrets() {
    local backup_file="$1"
    
    if [ -z "$backup_file" ]; then
        error "Backup file path is required"
        return 1
    fi
    
    if [ ! -f "$backup_file" ]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring secrets from: $backup_file"
    
    # Extract backup
    local temp_dir=$(mktemp -d)
    tar -xzf "$backup_file" -C "$temp_dir"
    
    # Find secrets directory in backup
    local secrets_backup_dir=$(find "$temp_dir" -name "secrets" -type d | head -1)
    
    if [ -z "$secrets_backup_dir" ]; then
        error "No secrets directory found in backup"
        rm -rf "$temp_dir"
        return 1
    fi
    
    # Backup current secrets
    backup_secrets
    
    # Restore secrets
    rm -rf "$SECRETS_DIR"
    cp -r "$secrets_backup_dir" "$SECRETS_DIR"
    
    # Clean up
    rm -rf "$temp_dir"
    
    log "✓ Secrets restored successfully"
}

# Function to audit secrets
audit_secrets() {
    log "Auditing secrets management..."
    
    local audit_report="$PROJECT_ROOT/logs/secrets-audit-$(date +%Y%m%d_%H%M%S).json"
    
    # Create audit report
    cat > "$audit_report" << EOF
{
  "audit_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "secrets_count": $(jq '.secrets | length' "$SECRETS_DIR/inventory.json" 2>/dev/null || echo "0"),
  "expired_secrets": [],
  "weak_secrets": [],
  "duplicate_secrets": [],
  "recommendations": []
}
EOF
    
    # Check for expired secrets
    check_expired_secrets
    local expired_count=$?
    
    # Update audit report with expired secrets
    if [ $expired_count -gt 0 ]; then
        jq --argjson expired_count $expired_count \
           '.expired_secrets_count = $expired_count' \
           "$audit_report" > "$audit_report.tmp" && \
           mv "$audit_report.tmp" "$audit_report"
    fi
    
    log "✓ Secrets audit completed: $audit_report"
}

# Function to generate environment variables
generate_env_vars() {
    local output_file="${1:-$PROJECT_ROOT/.env.generated}"
    
    log "Generating environment variables file..."
    
    if [ ! -f "$SECRETS_DIR/inventory.json" ]; then
        error "No secrets inventory found. Run 'initialize' first."
        return 1
    fi
    
    # Start with header
    cat > "$output_file" << EOF
# PA Ecosystem Environment Variables
# Generated by secrets manager on $(date)
# DO NOT EDIT MANUALLY - Use secrets-manager.sh to modify

EOF
    
    # Add each secret as environment variable
    while IFS= read -r secret_name; do
        local env_var_name=$(echo "$secret_name" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
        local secret_value=$(retrieve_secret "$secret_name")
        
        echo "$env_var_name=$secret_value" >> "$output_file"
    done < <(jq -r '.secrets | keys[]' "$SECRETS_DIR/inventory.json")
    
    # Set secure permissions
    chmod 600 "$output_file"
    
    log "✓ Environment variables generated: $output_file"
}

# Function to show help
show_help() {
    echo "PA Ecosystem Secrets Management Framework"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  initialize                    Initialize secrets management framework"
    echo "  store NAME VALUE [TYPE] [DAYS]  Store a new secret"
    echo "  retrieve NAME                Retrieve a secret value"
    echo "  list                         List all stored secrets"
    echo "  rotate NAME [NEW_VALUE]      Rotate an existing secret"
    echo "  check-expired                Check for expired secrets"
    echo "  backup                       Create backup of all secrets"
    echo "  restore BACKUP_FILE          Restore secrets from backup"
    echo "  audit                        Audit secrets management"
    echo "  generate-env [FILE]          Generate environment variables file"
    echo "  help                         Show this help message"
    echo ""
    echo "Options:"
    echo "  --force                      Force operation (e.g., regenerate master key)"
    echo "  --verbose                    Enable verbose output"
    echo ""
    echo "Examples:"
    echo "  $0 initialize                # Initialize secrets framework"
    echo "  $0 store postgres-password 'secure123' password 90"
    echo "  $0 retrieve postgres-password"
    echo "  $0 rotate api-key"
    echo "  $0 backup"
    echo "  $0 generate-env"
}

# Main function
main() {
    local command="$1"
    shift
    
    # Parse options
    while [[ $# -gt 0 ]]; do
        case $1 in
            --force)
                FORCE=true
                shift
                ;;
            --verbose)
                set -x
                shift
                ;;
            *)
                break
                ;;
        esac
    done
    
    # Initialize logging
    mkdir -p "$(dirname "$LOG_FILE")"
    
    log "Secrets Management Framework - $(date)"
    log "=================================="
    
    # Check prerequisites
    check_prerequisites
    
    # Execute command
    case "$command" in
        "initialize")
            initialize_secrets
            ;;
        "store")
            store_secret "$1" "$2" "$3" "$4"
            ;;
        "retrieve")
            retrieve_secret "$1"
            ;;
        "list")
            list_secrets
            ;;
        "rotate")
            rotate_secret "$1" "$2"
            ;;
        "check-expired")
            check_expired_secrets
            ;;
        "backup")
            backup_secrets
            ;;
        "restore")
            restore_secrets "$1"
            ;;
        "audit")
            audit_secrets
            ;;
        "generate-env")
            generate_env_vars "$1"
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
    
    log "Secrets management operation completed"
}

# Run main function
main "$@"
