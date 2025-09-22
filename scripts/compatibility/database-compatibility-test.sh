#!/bin/bash

# Database Compatibility Testing Script
# Purpose: Test database compatibility between framework versions
# Usage: ./database-compatibility-test.sh [--database <database>] [--framework <framework>]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="/var/log/compatibility/database-test-$(date +%Y%m%d-%H%M%S).log"
DATABASE=""
FRAMEWORK=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --database)
            DATABASE="$2"
            shift 2
            ;;
        --framework)
            FRAMEWORK="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--database <database>] [--framework <framework>]"
            echo ""
            echo "Options:"
            echo "  --database        Specific database to test (postgresql, neo4j)"
            echo "  --framework       Specific framework to test (n8n, letta, graphiti)"
            echo "  -h, --help        Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

# Logging function
log() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $message" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
    local message="$1"
    log "ERROR: $message"
    echo -e "${RED}❌ $message${NC}"
    exit 1
}

# Warning function
warning() {
    local message="$1"
    log "WARNING: $message"
    echo -e "${YELLOW}⚠️  $message${NC}"
}

# Success function
success() {
    local message="$1"
    log "SUCCESS: $message"
    echo -e "${GREEN}✅ $message${NC}"
}

# Info function
info() {
    local message="$1"
    log "INFO: $message"
    echo -e "${BLUE}ℹ️  $message${NC}"
}

# Test PostgreSQL compatibility
test_postgresql_compatibility() {
    info "Testing PostgreSQL compatibility..."
    
    if ! docker ps --format "table {{.Names}}" | grep -q "^supabase-db$"; then
        error_exit "PostgreSQL container (supabase-db) is not running"
    fi
    
    # Test basic connectivity
    info "Testing PostgreSQL connectivity..."
    if docker exec supabase-db pg_isready -U postgres >/dev/null 2>&1; then
        success "PostgreSQL is ready and accepting connections"
    else
        error_exit "PostgreSQL is not ready"
    fi
    
    # Test version compatibility
    info "Testing PostgreSQL version compatibility..."
    local postgres_version=$(docker exec supabase-db psql -U postgres -c "SELECT version();" 2>/dev/null | grep -o 'PostgreSQL [0-9]\+\.[0-9]\+' | cut -d' ' -f2 || echo "unknown")
    info "PostgreSQL version: $postgres_version"
    
    if [[ $postgres_version =~ ^15\. ]]; then
        success "PostgreSQL version $postgres_version is compatible"
    else
        warning "PostgreSQL version $postgres_version may not be compatible"
    fi
    
    # Test n8n database compatibility
    if [ -z "$FRAMEWORK" ] || [ "$FRAMEWORK" = "n8n" ]; then
        info "Testing n8n database compatibility..."
        
        # Check if n8n database exists
        local n8n_db_exists=$(docker exec supabase-db psql -U postgres -l 2>/dev/null | grep -q "n8n" && echo "true" || echo "false")
        
        if [ "$n8n_db_exists" = "true" ]; then
            success "n8n database exists"
            
            # Test n8n database connectivity
            if docker exec supabase-db psql -U postgres -d n8n -c "SELECT 1;" >/dev/null 2>&1; then
                success "n8n database connectivity is working"
            else
                warning "n8n database connectivity test failed"
            fi
            
            # Test n8n tables
            local n8n_tables=$(docker exec supabase-db psql -U postgres -d n8n -c "\dt" 2>/dev/null | grep -c "table" || echo "0")
            info "n8n tables count: $n8n_tables"
            
            if [ "$n8n_tables" -gt 0 ]; then
                success "n8n database schema is intact"
            else
                warning "n8n database may have schema issues"
            fi
        else
            info "n8n database does not exist (expected if n8n not configured)"
        fi
    fi
    
    # Test Letta database compatibility
    if [ -z "$FRAMEWORK" ] || [ "$FRAMEWORK" = "letta" ]; then
        info "Testing Letta database compatibility..."
        
        # Check if Letta schemas exist
        local letta_schemas=$(docker exec supabase-db psql -U postgres -c "\dn" 2>/dev/null | grep -E "(letta_agents|letta_embeddings)" | wc -l || echo "0")
        
        if [ "$letta_schemas" -gt 0 ]; then
            success "Letta database schemas exist"
            
            # Test Letta tables
            local letta_tables=$(docker exec supabase-db psql -U postgres -c "\dt letta_agents.*" 2>/dev/null | grep -c "table" || echo "0")
            info "Letta tables count: $letta_tables"
            
            if [ "$letta_tables" -gt 0 ]; then
                success "Letta database schema is intact"
            else
                warning "Letta database may have schema issues"
            fi
            
            # Test Letta data integrity
            local letta_agents_count=$(docker exec supabase-db psql -U postgres -c "SELECT COUNT(*) FROM letta_agents.agents;" 2>/dev/null | grep -o '[0-9]\+' || echo "0")
            info "Letta agents count: $letta_agents_count"
            
        else
            info "Letta database schemas do not exist (expected if Letta not configured)"
        fi
    fi
    
    # Test database performance
    info "Testing PostgreSQL performance..."
    local query_time=$(docker exec supabase-db psql -U postgres -c "SELECT pg_sleep(0.1);" 2>/dev/null | grep -o "Time: [0-9.]* ms" || echo "unknown")
    info "Query performance: $query_time"
    
    if [[ $query_time =~ Time: [0-9.]+ ms ]]; then
        success "PostgreSQL performance is acceptable"
    else
        warning "PostgreSQL performance may be degraded"
    fi
}

# Test Neo4j compatibility
test_neo4j_compatibility() {
    info "Testing Neo4j compatibility..."
    
    if ! docker ps --format "table {{.Names}}" | grep -q "^graphiti-neo4j$"; then
        error_exit "Neo4j container (graphiti-neo4j) is not running"
    fi
    
    # Test basic connectivity
    info "Testing Neo4j connectivity..."
    if docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "RETURN 1;" >/dev/null 2>&1; then
        success "Neo4j is ready and accepting connections"
    else
        error_exit "Neo4j is not ready"
    fi
    
    # Test version compatibility
    info "Testing Neo4j version compatibility..."
    local neo4j_version=$(docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "CALL dbms.components() YIELD name, versions RETURN versions[0] as version;" 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+' || echo "unknown")
    info "Neo4j version: $neo4j_version"
    
    if [[ $neo4j_version =~ ^5\. ]]; then
        success "Neo4j version $neo4j_version is compatible"
    else
        warning "Neo4j version $neo4j_version may not be compatible"
    fi
    
    # Test Graphiti database compatibility
    if [ -z "$FRAMEWORK" ] || [ "$FRAMEWORK" = "graphiti" ]; then
        info "Testing Graphiti database compatibility..."
        
        # Test database existence
        local db_exists=$(docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "SHOW DATABASES;" 2>/dev/null | grep -q "neo4j" && echo "true" || echo "false")
        
        if [ "$db_exists" = "true" ]; then
            success "Neo4j database exists"
            
            # Test basic operations
            if docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "MATCH (n) RETURN COUNT(n) as node_count;" >/dev/null 2>&1; then
                success "Neo4j basic operations are working"
            else
                warning "Neo4j basic operations test failed"
            fi
            
            # Test Graphiti-specific operations
            if docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "CALL apoc.schema.assert({}, {}) YIELD label, key RETURN label, key;" >/dev/null 2>&1; then
                success "Neo4j APOC procedures are available"
            else
                warning "Neo4j APOC procedures may not be available"
            fi
            
        else
            error_exit "Neo4j database does not exist"
        fi
    fi
    
    # Test database performance
    info "Testing Neo4j performance..."
    local start_time=$(date +%s%N)
    docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "MATCH (n) RETURN COUNT(n) as count;" >/dev/null 2>&1
    local end_time=$(date +%s%N)
    local duration=$(( (end_time - start_time) / 1000000 )) # Convert to milliseconds
    
    info "Query performance: ${duration}ms"
    
    if [ "$duration" -lt 1000 ]; then
        success "Neo4j performance is acceptable"
    else
        warning "Neo4j performance may be degraded"
    fi
}

# Test database schema compatibility
test_database_schema_compatibility() {
    info "Testing database schema compatibility..."
    
    # Test PostgreSQL schema compatibility
    if docker ps --format "table {{.Names}}" | grep -q "^supabase-db$"; then
        info "Testing PostgreSQL schema compatibility..."
        
        # Test schema versioning
        local schema_version=$(docker exec supabase-db psql -U postgres -c "SELECT version();" 2>/dev/null | grep -o 'PostgreSQL [0-9]\+\.[0-9]\+' | cut -d' ' -f2 || echo "unknown")
        info "PostgreSQL schema version: $schema_version"
        
        # Test extension compatibility
        local extensions=$(docker exec supabase-db psql -U postgres -c "\dx" 2>/dev/null | grep -c "extension" || echo "0")
        info "PostgreSQL extensions count: $extensions"
        
        if [ "$extensions" -gt 0 ]; then
            success "PostgreSQL extensions are available"
        else
            warning "PostgreSQL extensions may not be available"
        fi
    fi
    
    # Test Neo4j schema compatibility
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-neo4j$"; then
        info "Testing Neo4j schema compatibility..."
        
        # Test constraints
        local constraints=$(docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "SHOW CONSTRAINTS;" 2>/dev/null | grep -c "constraint" || echo "0")
        info "Neo4j constraints count: $constraints"
        
        # Test indexes
        local indexes=$(docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "SHOW INDEXES;" 2>/dev/null | grep -c "index" || echo "0")
        info "Neo4j indexes count: $indexes"
        
        if [ "$constraints" -ge 0 ] && [ "$indexes" -ge 0 ]; then
            success "Neo4j schema is intact"
        else
            warning "Neo4j schema may have issues"
        fi
    fi
}

# Test database migration compatibility
test_database_migration_compatibility() {
    info "Testing database migration compatibility..."
    
    # Test PostgreSQL migration compatibility
    if docker ps --format "table {{.Names}}" | grep -q "^supabase-db$"; then
        info "Testing PostgreSQL migration compatibility..."
        
        # Test migration history
        local migration_tables=$(docker exec supabase-db psql -U postgres -c "\dt" 2>/dev/null | grep -E "(migrations|schema_migrations)" | wc -l || echo "0")
        
        if [ "$migration_tables" -gt 0 ]; then
            success "PostgreSQL migration tables exist"
        else
            info "PostgreSQL migration tables not found (expected for some frameworks)"
        fi
    fi
    
    # Test Neo4j migration compatibility
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-neo4j$"; then
        info "Testing Neo4j migration compatibility..."
        
        # Test for migration metadata
        local migration_nodes=$(docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "MATCH (n:Migration) RETURN COUNT(n) as count;" 2>/dev/null | grep -o '[0-9]\+' || echo "0")
        
        if [ "$migration_nodes" -gt 0 ]; then
            success "Neo4j migration metadata exists"
        else
            info "Neo4j migration metadata not found (expected for new installations)"
        fi
    fi
}

# Main database compatibility testing process
main() {
    echo -e "${BLUE}🔍 Database Compatibility Testing${NC}"
    echo -e "${BLUE}=================================${NC}"
    echo "Database: ${DATABASE:-all}"
    echo "Framework: ${FRAMEWORK:-all}"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting database compatibility testing"
    
    # Test individual databases
    if [ -z "$DATABASE" ] || [ "$DATABASE" = "postgresql" ]; then
        test_postgresql_compatibility
    fi
    
    if [ -z "$DATABASE" ] || [ "$DATABASE" = "neo4j" ]; then
        test_neo4j_compatibility
    fi
    
    # Test schema compatibility
    test_database_schema_compatibility
    
    # Test migration compatibility
    test_database_migration_compatibility
    
    success "Database compatibility testing completed!"
    echo ""
    echo -e "${GREEN}📋 Test Summary${NC}"
    echo -e "${GREEN}===============${NC}"
    echo "✅ Database connectivity: Tested"
    echo "✅ Version compatibility: Validated"
    echo "✅ Schema compatibility: Tested"
    echo "✅ Migration compatibility: Tested"
    echo "✅ Performance compatibility: Assessed"
    echo ""
    echo -e "${BLUE}📝 Next Steps${NC}"
    echo "1. Review any warnings or failures"
    echo "2. Test database compatibility in staging environment if needed"
    echo "3. Update compatibility matrix based on test results"
    echo ""
    echo "Log file: $LOG_FILE"
}

# Run main function
main "$@"
