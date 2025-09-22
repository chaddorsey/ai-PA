#!/bin/bash

# Version Detection Script for PA Ecosystem
# Purpose: Detect actual running versions of services using 'latest' tags
# Usage: ./detect-versions.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
OUTPUT_FILE="/Users/chaddorsey/Dropbox/dev/ai-PA/config/versions/detected-versions.yml"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo -e "${BLUE}🔍 PA Ecosystem Version Detection${NC}"
echo -e "${BLUE}================================${NC}"
echo "Timestamp: $TIMESTAMP"
echo ""

# Create output directory if it doesn't exist
mkdir -p "$(dirname "$OUTPUT_FILE")"

# Initialize output file
cat > "$OUTPUT_FILE" << EOF
# Detected Versions - PA Ecosystem
# Generated: $TIMESTAMP
# Purpose: Actual running versions detected from containers

detection_timestamp: "$TIMESTAMP"
detection_method: "container_inspection"

services:
EOF

# Function to detect version from container
detect_container_version() {
    local container_name=$1
    local service_name=$2
    
    echo -e "${YELLOW}🔍 Detecting version for $service_name...${NC}"
    
    if docker ps --format "table {{.Names}}" | grep -q "^${container_name}$"; then
        # Container is running
        local image_id=$(docker inspect --format='{{.Image}}' "$container_name")
        local image_info=$(docker inspect --format='{{.Config.Image}}' "$container_name")
        local created_date=$(docker inspect --format='{{.Created}}' "$container_name")
        
        echo "  $service_name:" >> "$OUTPUT_FILE"
        echo "    container_name: \"$container_name\"" >> "$OUTPUT_FILE"
        echo "    image_id: \"$image_id\"" >> "$OUTPUT_FILE"
        echo "    image_tag: \"$image_info\"" >> "$OUTPUT_FILE"
        echo "    created_date: \"$created_date\"" >> "$OUTPUT_FILE"
        
        # Try to extract version from container environment or labels
        local version_info=$(docker inspect --format='{{range .Config.Env}}{{println .}}{{end}}' "$container_name" | grep -i version || echo "not_found")
        if [ "$version_info" != "not_found" ]; then
            echo "    detected_version: \"$version_info\"" >> "$OUTPUT_FILE"
        else
            echo "    detected_version: \"unknown\"" >> "$OUTPUT_FILE"
        fi
        
        echo -e "${GREEN}✅ $service_name: $image_info${NC}"
    else
        echo "  $service_name:" >> "$OUTPUT_FILE"
        echo "    status: \"not_running\"" >> "$OUTPUT_FILE"
        echo "    container_name: \"$container_name\"" >> "$OUTPUT_FILE"
        echo -e "${RED}❌ $service_name: Container not running${NC}"
    fi
    echo "" >> "$OUTPUT_FILE"
}

# Function to detect version from package.json (for Node.js services)
detect_nodejs_version() {
    local service_path=$1
    local service_name=$2
    
    echo -e "${YELLOW}🔍 Detecting Node.js version for $service_name...${NC}"
    
    if [ -f "$service_path/package.json" ]; then
        local version=$(grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' "$service_path/package.json" | cut -d'"' -f4)
        echo "  $service_name:" >> "$OUTPUT_FILE"
        echo "    type: \"nodejs\"" >> "$OUTPUT_FILE"
        echo "    package_version: \"$version\"" >> "$OUTPUT_FILE"
        echo "    package_path: \"$service_path/package.json\"" >> "$OUTPUT_FILE"
        echo -e "${GREEN}✅ $service_name: $version${NC}"
    else
        echo "  $service_name:" >> "$OUTPUT_FILE"
        echo "    type: \"nodejs\"" >> "$OUTPUT_FILE"
        echo "    package_version: \"not_found\"" >> "$OUTPUT_FILE"
        echo "    package_path: \"$service_path/package.json\"" >> "$OUTPUT_FILE"
        echo -e "${RED}❌ $service_name: package.json not found${NC}"
    fi
    echo "" >> "$OUTPUT_FILE"
}

# Function to detect version from pyproject.toml (for Python services)
detect_python_version() {
    local service_path=$1
    local service_name=$2
    
    echo -e "${YELLOW}🔍 Detecting Python version for $service_name...${NC}"
    
    if [ -f "$service_path/pyproject.toml" ]; then
        local version=$(grep -o 'version[[:space:]]*=[[:space:]]*"[^"]*"' "$service_path/pyproject.toml" | cut -d'"' -f2)
        echo "  $service_name:" >> "$OUTPUT_FILE"
        echo "    type: \"python\"" >> "$OUTPUT_FILE"
        echo "    pyproject_version: \"$version\"" >> "$OUTPUT_FILE"
        echo "    pyproject_path: \"$service_path/pyproject.toml\"" >> "$OUTPUT_FILE"
        echo -e "${GREEN}✅ $service_name: $version${NC}"
    else
        echo "  $service_name:" >> "$OUTPUT_FILE"
        echo "    type: \"python\"" >> "$OUTPUT_FILE"
        echo "    pyproject_version: \"not_found\"" >> "$OUTPUT_FILE"
        echo "    pyproject_path: \"$service_path/pyproject.toml\"" >> "$OUTPUT_FILE"
        echo -e "${RED}❌ $service_name: pyproject.toml not found${NC}"
    fi
    echo "" >> "$OUTPUT_FILE"
}

# Detect versions for Docker containers
echo -e "${BLUE}📦 Detecting Docker Container Versions${NC}"
echo -e "${BLUE}====================================${NC}"

detect_container_version "n8n" "n8n"
detect_container_version "letta" "letta"
detect_container_version "cloudflared" "cloudflared"
detect_container_version "cloudflare-tunnel" "cloudflare-tunnel"
detect_container_version "open-webui" "open-webui"
detect_container_version "supabase-db" "supabase-db"
detect_container_version "neo4j" "graphiti-neo4j"
detect_container_version "gmail-mcp-server" "gmail-mcp-server"
detect_container_version "graphiti-mcp-server" "graphiti-mcp-server"
detect_container_version "rag-mcp-server" "rag-mcp-server"
detect_container_version "slackbot" "slackbot"
detect_container_version "health-monitor" "health-monitor"

# Detect versions for custom built services
echo -e "${BLUE}🛠️  Detecting Custom Built Service Versions${NC}"
echo -e "${BLUE}=========================================${NC}"

detect_nodejs_version "/Users/chaddorsey/Dropbox/dev/ai-PA/health-monitor" "health-monitor"
detect_nodejs_version "/Users/chaddorsey/Dropbox/dev/ai-PA/gmail-mcp" "gmail-mcp"
detect_nodejs_version "/Users/chaddorsey/Dropbox/dev/ai-PA/rag-mcp" "rag-mcp"
detect_python_version "/Users/chaddorsey/Dropbox/dev/ai-PA/graphiti" "graphiti"

# Add summary to output file
cat >> "$OUTPUT_FILE" << EOF

# Summary
summary:
  total_services_checked: 16
  detection_timestamp: "$TIMESTAMP"
  next_steps:
    - "Review detected versions"
    - "Update versions.lock.yml with actual versions"
    - "Pin services currently using 'latest' tags"
    - "Create upgrade procedures for each service"

# Notes
notes:
  - "Services using 'latest' tags need version pinning"
  - "Custom built services should have version tags in their build processes"
  - "Regular version detection should be automated"
EOF

echo ""
echo -e "${GREEN}✅ Version detection complete!${NC}"
echo -e "${GREEN}📄 Results saved to: $OUTPUT_FILE${NC}"
echo ""
echo -e "${YELLOW}📋 Next Steps:${NC}"
echo "1. Review the detected versions"
echo "2. Update versions.lock.yml with actual versions"
echo "3. Pin services currently using 'latest' tags"
echo "4. Create upgrade procedures for each service"
echo ""
echo -e "${BLUE}🔍 To view results:${NC}"
echo "cat $OUTPUT_FILE"
