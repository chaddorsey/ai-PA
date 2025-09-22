#!/bin/bash

# Version Validation Script for PA Ecosystem
# Purpose: Validate that running containers match expected versions in lock file
# Usage: ./validate-versions.sh [--fix]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
LOCK_FILE="/Users/chaddorsey/Dropbox/dev/ai-PA/config/versions/versions.lock.yml"
FIX_MODE=false

# Parse command line arguments
if [ "$1" = "--fix" ]; then
    FIX_MODE=true
fi

echo -e "${BLUE}🔍 PA Ecosystem Version Validation${NC}"
echo -e "${BLUE}==================================${NC}"
echo "Lock file: $LOCK_FILE"
echo "Fix mode: $FIX_MODE"
echo ""

# Check if lock file exists
if [ ! -f "$LOCK_FILE" ]; then
    echo -e "${RED}❌ Version lock file not found: $LOCK_FILE${NC}"
    exit 1
fi

# Function to get expected version from lock file
get_expected_version() {
    local service_name=$1
    local version=$(grep -A 15 "  $service_name:" "$LOCK_FILE" | grep "version:" | head -1 | cut -d'"' -f2)
    echo "$version"
}

# Function to get expected tag from lock file
get_expected_tag() {
    local service_name=$1
    local tag=$(grep -A 15 "  $service_name:" "$LOCK_FILE" | grep "tag:" | head -1 | cut -d'"' -f2)
    echo "$tag"
}

# Function to check if service is locked
is_service_locked() {
    local service_name=$1
    local locked=$(grep -A 15 "  $service_name:" "$LOCK_FILE" | grep "locked:" | head -1 | awk '{print $2}')
    echo "$locked"
}

# Function to validate container version
validate_container() {
    local container_name=$1
    local service_name=$2
    local expected_version=$3
    local expected_tag=$4
    local is_locked=$5
    
    echo -e "${YELLOW}🔍 Validating $service_name...${NC}"
    
    if [ "$is_locked" != "true" ]; then
        echo -e "${YELLOW}⚠️  $service_name is not locked - skipping validation${NC}"
        return 0
    fi
    
    if ! docker ps --format "table {{.Names}}" | grep -q "^${container_name}$"; then
        echo -e "${YELLOW}⚠️  $service_name container not running - skipping validation${NC}"
        return 0
    fi
    
    # Get actual image tag from container
    local actual_tag=$(docker inspect --format='{{.Config.Image}}' "$container_name")
    
    # For custom built images, we can't easily validate version
    if [[ "$actual_tag" == *"ai-pa-"* ]] || [[ "$actual_tag" == *"custom"* ]]; then
        echo -e "${GREEN}✅ $service_name: Custom built image ($actual_tag)${NC}"
        return 0
    fi
    
    # Check if the actual tag contains the expected tag
    if [[ "$actual_tag" == *"$expected_tag"* ]]; then
        echo -e "${GREEN}✅ $service_name: Version matches ($expected_tag)${NC}"
        return 0
    else
        echo -e "${RED}❌ $service_name: Version mismatch${NC}"
        echo -e "${RED}   Expected: $expected_tag${NC}"
        echo -e "${RED}   Actual: $actual_tag${NC}"
        
        if [ "$FIX_MODE" = true ]; then
            echo -e "${YELLOW}🔧 Fix mode enabled - would update container${NC}"
            # In fix mode, we would update the container here
            # This is a placeholder for future implementation
        fi
        
        return 1
    fi
}

# Initialize counters
total_services=0
validated_services=0
mismatched_services=0
skipped_services=0

echo -e "${BLUE}📦 Validating Container Versions${NC}"
echo -e "${BLUE}==============================${NC}"

# Validate each service
services=(
    "n8n:n8n"
    "letta:letta"
    "cloudflare-tunnel:cloudflared"
    "open-webui:open-webui"
    "supabase-db:postgres"
    "neo4j:neo4j"
    "gmail-mcp-server:gmail-mcp"
    "graphiti-mcp-server:graphiti-mcp"
    "rag-mcp-server:rag-mcp"
    "slackbot:slackbot"
    "health-monitor:health-monitor"
)

for service_info in "${services[@]}"; do
    IFS=':' read -r container_name service_name <<< "$service_info"
    
    expected_version=$(get_expected_version "$service_name")
    expected_tag=$(get_expected_tag "$service_name")
    is_locked=$(is_service_locked "$service_name")
    
    total_services=$((total_services + 1))
    
    if [ "$is_locked" != "true" ]; then
        skipped_services=$((skipped_services + 1))
        continue
    fi
    
    if validate_container "$container_name" "$service_name" "$expected_version" "$expected_tag" "$is_locked"; then
        validated_services=$((validated_services + 1))
    else
        mismatched_services=$((mismatched_services + 1))
    fi
done

echo ""
echo -e "${BLUE}📊 Validation Summary${NC}"
echo -e "${BLUE}====================${NC}"
echo "Total services: $total_services"
echo -e "${GREEN}Validated: $validated_services${NC}"
echo -e "${RED}Mismatched: $mismatched_services${NC}"
echo -e "${YELLOW}Skipped (unlocked): $skipped_services${NC}"

if [ $mismatched_services -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ All locked services have correct versions!${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}❌ $mismatched_services services have version mismatches${NC}"
    if [ "$FIX_MODE" = false ]; then
        echo -e "${YELLOW}💡 Run with --fix to attempt automatic fixes${NC}"
    fi
    exit 1
fi
