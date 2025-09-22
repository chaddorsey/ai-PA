#!/bin/bash

# PA Ecosystem Credential Audit Script
# Identifies hardcoded credentials and security vulnerabilities
# Created: 2025-01-21

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
AUDIT_DIR="$PROJECT_ROOT/logs/audits"
REPORT_FILE="$AUDIT_DIR/credential-audit-$(date +%Y%m%d_%H%M%S).json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log messages
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

# Function to create audit report structure
create_audit_report() {
    mkdir -p "$AUDIT_DIR"
    
    cat > "$REPORT_FILE" << EOF
{
  "audit_metadata": {
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "auditor": "credential-audit.sh",
    "project_root": "$PROJECT_ROOT",
    "scan_type": "credential_security_audit"
  },
  "summary": {
    "total_files_scanned": 0,
    "hardcoded_credentials": 0,
    "weak_passwords": 0,
    "exposed_api_keys": 0,
    "security_violations": 0
  },
  "findings": {
    "hardcoded_passwords": [],
    "api_keys": [],
    "database_credentials": [],
    "weak_secrets": [],
    "security_violations": []
  },
  "recommendations": []
}
EOF
}

# Function to update audit report
update_audit_report() {
    local field="$1"
    local value="$2"
    
    jq --arg field "$field" --arg value "$value" \
       ".summary[$field] = (.summary[$field] + 1)" \
       "$REPORT_FILE" > "$REPORT_FILE.tmp" && \
       mv "$REPORT_FILE.tmp" "$REPORT_FILE"
}

# Function to add finding to report
add_finding() {
    local category="$1"
    local finding="$2"
    
    jq --arg category "$category" --argjson finding "$finding" \
       ".findings[$category] += [$finding]" \
       "$REPORT_FILE" > "$REPORT_FILE.tmp" && \
       mv "$REPORT_FILE.tmp" "$REPORT_FILE"
}

# Function to scan file for hardcoded credentials
scan_file() {
    local file_path="$1"
    local relative_path="${file_path#$PROJECT_ROOT/}"
    
    log "Scanning: $relative_path"
    
    # Update total files scanned
    jq '.summary.total_files_scanned += 1' "$REPORT_FILE" > "$REPORT_FILE.tmp" && \
       mv "$REPORT_FILE.tmp" "$REPORT_FILE"
    
    # Common password patterns
    local password_patterns=(
        "password.*=.*['\"][^'\"]{1,20}['\"]"
        "passwd.*=.*['\"][^'\"]{1,20}['\"]"
        "pwd.*=.*['\"][^'\"]{1,20}['\"]"
        "secret.*=.*['\"][^'\"]{1,20}['\"]"
        "token.*=.*['\"][^'\"]{1,50}['\"]"
        "key.*=.*['\"][^'\"]{1,50}['\"]"
        "api_key.*=.*['\"][^'\"]{1,50}['\"]"
        "apikey.*=.*['\"][^'\"]{1,50}['\"]"
        "access_token.*=.*['\"][^'\"]{1,50}['\"]"
        "auth.*=.*['\"][^'\"]{1,50}['\"]"
    )
    
    # Database credential patterns
    local db_patterns=(
        "postgres_password.*=.*['\"][^'\"]{1,50}['\"]"
        "mysql_password.*=.*['\"][^'\"]{1,50}['\"]"
        "db_password.*=.*['\"][^'\"]{1,50}['\"]"
        "database_password.*=.*['\"][^'\"]{1,50}['\"]"
        "mongodb_password.*=.*['\"][^'\"]{1,50}['\"]"
    )
    
    # API key patterns
    local api_patterns=(
        "sk-[a-zA-Z0-9]{20,}"
        "pk_[a-zA-Z0-9]{20,}"
        "xoxb-[a-zA-Z0-9-]+"
        "xoxp-[a-zA-Z0-9-]+"
        "xoxa-[a-zA-Z0-9-]+"
        "AIza[0-9A-Za-z-_]{35}"
        "ya29\.[0-9A-Za-z-_]+"
    )
    
    # Check for password patterns
    for pattern in "${password_patterns[@]}"; do
        while IFS= read -r line; do
            local line_number=$(echo "$line" | cut -d: -f1)
            local content=$(echo "$line" | cut -d: -f2-)
            
            # Skip if it's a template or example
            if [[ "$content" =~ (example|template|placeholder|your_|replace|TODO) ]]; then
                continue
            fi
            
            local finding=$(jq -n \
                --arg file "$relative_path" \
                --arg line "$line_number" \
                --arg content "$(echo "$content" | sed 's/"/\\"/g')" \
                --arg pattern "$pattern" \
                '{
                    file: $file,
                    line: $line,
                    content: $content,
                    pattern: $pattern,
                    severity: "high",
                    type: "hardcoded_password"
                }')
            
            add_finding "hardcoded_passwords" "$finding"
            update_audit_report "hardcoded_credentials" "1"
            
        done < <(grep -n -i "$pattern" "$file_path" 2>/dev/null || true)
    done
    
    # Check for database credential patterns
    for pattern in "${db_patterns[@]}"; do
        while IFS= read -r line; do
            local line_number=$(echo "$line" | cut -d: -f1)
            local content=$(echo "$line" | cut -d: -f2-)
            
            if [[ "$content" =~ (example|template|placeholder|your_|replace|TODO) ]]; then
                continue
            fi
            
            local finding=$(jq -n \
                --arg file "$relative_path" \
                --arg line "$line_number" \
                --arg content "$(echo "$content" | sed 's/"/\\"/g')" \
                --arg pattern "$pattern" \
                '{
                    file: $file,
                    line: $line,
                    content: $content,
                    pattern: $pattern,
                    severity: "critical",
                    type: "database_credential"
                }')
            
            add_finding "database_credentials" "$finding"
            update_audit_report "hardcoded_credentials" "1"
            
        done < <(grep -n -i "$pattern" "$file_path" 2>/dev/null || true)
    done
    
    # Check for API key patterns
    for pattern in "${api_patterns[@]}"; do
        while IFS= read -r line; do
            local line_number=$(echo "$line" | cut -d: -f1)
            local content=$(echo "$line" | cut -d: -f2-)
            
            if [[ "$content" =~ (example|template|placeholder|your_|replace|TODO) ]]; then
                continue
            fi
            
            local finding=$(jq -n \
                --arg file "$relative_path" \
                --arg line "$line_number" \
                --arg content "$(echo "$content" | sed 's/"/\\"/g')" \
                --arg pattern "$pattern" \
                '{
                    file: $file,
                    line: $line,
                    content: $content,
                    pattern: $pattern,
                    severity: "critical",
                    type: "exposed_api_key"
                }')
            
            add_finding "api_keys" "$finding"
            update_audit_report "exposed_api_keys" "1"
            
        done < <(grep -n "$pattern" "$file_path" 2>/dev/null || true)
    done
    
    # Check for weak passwords (common passwords)
    local weak_passwords=(
        "password"
        "123456"
        "admin"
        "root"
        "test"
        "guest"
        "user"
        "default"
        "changeme"
        "secret"
        "qwerty"
        "abc123"
        "password123"
        "admin123"
        "root123"
    )
    
    for weak_pass in "${weak_passwords[@]}"; do
        while IFS= read -r line; do
            local line_number=$(echo "$line" | cut -d: -f1)
            local content=$(echo "$line" | cut -d: -f2-)
            
            local finding=$(jq -n \
                --arg file "$relative_path" \
                --arg line "$line_number" \
                --arg content "$(echo "$content" | sed 's/"/\\"/g')" \
                --arg password "$weak_pass" \
                '{
                    file: $file,
                    line: $line,
                    content: $content,
                    password: $password,
                    severity: "high",
                    type: "weak_password"
                }')
            
            add_finding "weak_secrets" "$finding"
            update_audit_report "weak_passwords" "1"
            
        done < <(grep -n -i "['\"]$weak_pass['\"]" "$file_path" 2>/dev/null || true)
    done
}

# Function to check file permissions
check_file_permissions() {
    log "Checking file permissions for sensitive files..."
    
    local sensitive_files=(
        ".env"
        "docker-compose.yml"
        "*.key"
        "*.pem"
        "*.p12"
        "credentials.json"
        "config.json"
    )
    
    for pattern in "${sensitive_files[@]}"; do
        while IFS= read -r file; do
            if [ -f "$file" ]; then
                local perms=$(stat -c "%a" "$file")
                local relative_path="${file#$PROJECT_ROOT/}"
                
                # Check if file has overly permissive permissions
                if [[ "$perms" =~ ^[67][67][67]$ ]] || [[ "$perms" =~ ^[67][67][67][67]$ ]]; then
                    local finding=$(jq -n \
                        --arg file "$relative_path" \
                        --arg permissions "$perms" \
                        '{
                            file: $file,
                            permissions: $permissions,
                            severity: "medium",
                            type: "insecure_permissions"
                        }')
                    
                    add_finding "security_violations" "$finding"
                    update_audit_report "security_violations" "1"
                fi
            fi
        done < <(find "$PROJECT_ROOT" -name "$pattern" -type f 2>/dev/null || true)
    done
}

# Function to scan all relevant files
scan_project() {
    log "Starting credential audit scan..."
    
    # File extensions to scan
    local extensions=(
        ".sh"
        ".py"
        ".js"
        ".ts"
        ".json"
        ".yml"
        ".yaml"
        ".env"
        ".conf"
        ".cfg"
        ".ini"
        ".xml"
        ".properties"
    )
    
    # Directories to exclude
    local exclude_dirs=(
        "node_modules"
        ".git"
        "dist"
        "build"
        "target"
        "__pycache__"
        ".pytest_cache"
        "logs"
        "backups"
    )
    
    # Build find command with exclusions
    local find_cmd="find '$PROJECT_ROOT' -type f"
    
    for ext in "${extensions[@]}"; do
        find_cmd="$find_cmd \\( -name '*$ext'"
    done
    find_cmd="$find_cmd \\)"
    
    for dir in "${exclude_dirs[@]}"; do
        find_cmd="$find_cmd -not -path '*/$dir/*'"
    done
    
    # Execute find and scan files
    eval "$find_cmd" | while read -r file; do
        scan_file "$file"
    done
    
    # Check file permissions
    check_file_permissions
}

# Function to generate recommendations
generate_recommendations() {
    log "Generating security recommendations..."
    
    local recommendations=()
    
    # Get summary counts
    local hardcoded_count=$(jq '.summary.hardcoded_credentials' "$REPORT_FILE")
    local api_keys_count=$(jq '.summary.exposed_api_keys' "$REPORT_FILE")
    local weak_count=$(jq '.summary.weak_passwords' "$REPORT_FILE")
    local violations_count=$(jq '.summary.security_violations' "$REPORT_FILE")
    
    # Generate recommendations based on findings
    if [ "$hardcoded_count" -gt 0 ]; then
        recommendations+=('{
            "category": "secrets_management",
            "priority": "critical",
            "title": "Implement Secrets Management Framework",
            "description": "Replace all hardcoded credentials with environment variables or secrets management system",
            "action": "Use the secrets-manager.sh script to store credentials securely"
        }')
    fi
    
    if [ "$api_keys_count" -gt 0 ]; then
        recommendations+=('{
            "category": "api_security",
            "priority": "critical",
            "title": "Secure API Key Storage",
            "description": "Move API keys to secure environment variables or secrets management",
            "action": "Store API keys using secrets-manager.sh and reference via environment variables"
        }')
    fi
    
    if [ "$weak_count" -gt 0 ]; then
        recommendations+=('{
            "category": "password_security",
            "priority": "high",
            "title": "Replace Weak Passwords",
            "description": "Replace all weak or default passwords with strong, unique passwords",
            "action": "Generate strong passwords using secrets-manager.sh generate-secret command"
        }')
    fi
    
    if [ "$violations_count" -gt 0 ]; then
        recommendations+=('{
            "category": "file_security",
            "priority": "medium",
            "title": "Fix File Permissions",
            "description": "Set appropriate file permissions for sensitive configuration files",
            "action": "Use chmod 600 for sensitive files, chmod 644 for configuration files"
        }')
    fi
    
    # Add general recommendations
    recommendations+=('{
        "category": "general_security",
        "priority": "medium",
        "title": "Implement Security Best Practices",
        "description": "Follow security best practices for credential management",
        "action": "Review and implement security guidelines in docs/security/"
    }')
    
    # Update report with recommendations
    local recommendations_json=$(printf '%s\n' "${recommendations[@]}" | jq -s .)
    jq --argjson recommendations "$recommendations_json" \
       '.recommendations = $recommendations' \
       "$REPORT_FILE" > "$REPORT_FILE.tmp" && \
       mv "$REPORT_FILE.tmp" "$REPORT_FILE"
}

# Function to print summary
print_summary() {
    log "Credential Audit Summary"
    log "======================"
    
    local total_files=$(jq '.summary.total_files_scanned' "$REPORT_FILE")
    local hardcoded=$(jq '.summary.hardcoded_credentials' "$REPORT_FILE")
    local api_keys=$(jq '.summary.exposed_api_keys' "$REPORT_FILE")
    local weak=$(jq '.summary.weak_passwords' "$REPORT_FILE")
    local violations=$(jq '.summary.security_violations' "$REPORT_FILE")
    
    echo "Files Scanned: $total_files"
    echo "Hardcoded Credentials: $hardcoded"
    echo "Exposed API Keys: $api_keys"
    echo "Weak Passwords: $weak"
    echo "Security Violations: $violations"
    echo ""
    
    if [ "$hardcoded" -gt 0 ] || [ "$api_keys" -gt 0 ] || [ "$weak" -gt 0 ]; then
        warning "Security issues found! Review the detailed report: $REPORT_FILE"
        echo ""
        echo "Top Recommendations:"
        jq -r '.recommendations[] | "- \(.title): \(.description)"' "$REPORT_FILE" | head -5
    else
        log "✓ No security issues found in credential audit"
    fi
}

# Function to show help
show_help() {
    echo "PA Ecosystem Credential Audit Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --output FILE          Specify output file for audit report"
    echo "  --verbose              Enable verbose output"
    echo "  --help                 Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                     # Run full credential audit"
    echo "  $0 --output custom-report.json"
}

# Main function
main() {
    local output_file=""
    local verbose=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --output)
                output_file="$2"
                shift 2
                ;;
            --verbose)
                verbose=true
                set -x
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # Set output file if specified
    if [ -n "$output_file" ]; then
        REPORT_FILE="$output_file"
    fi
    
    log "PA Ecosystem Credential Audit"
    log "============================"
    log "Project Root: $PROJECT_ROOT"
    log "Report File: $REPORT_FILE"
    echo ""
    
    # Create audit report
    create_audit_report
    
    # Scan project for credentials
    scan_project
    
    # Generate recommendations
    generate_recommendations
    
    # Print summary
    print_summary
    
    log "Credential audit completed successfully"
}

# Run main function
main "$@"
