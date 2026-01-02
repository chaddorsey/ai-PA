#!/bin/bash
#
# Start Sports & Media Control Services
# Starts sports-service and flipper-api containers
#

set -e

echo "=========================================="
echo "Starting Sports & Media Control Services"
echo "=========================================="
echo ""

# Navigate to project root
cd "$(dirname "$0")/../.."

# Build and start services
echo "Building and starting services..."
docker-compose up -d --build sports-service flipper-api

echo ""
echo "Waiting for services to start..."
sleep 10

echo ""
echo "Checking service health..."

# Check sports-service
if curl -s http://localhost:5123/health | grep -q "healthy"; then
    echo "✓ sports-service is healthy"
else
    echo "✗ sports-service health check failed"
fi

# Check flipper-api
if curl -s http://localhost:5124/health | grep -q "flipper-api"; then
    echo "✓ flipper-api is running"
else
    echo "✗ flipper-api health check failed"
fi

echo ""
echo "=========================================="
echo "Services Started"
echo "=========================================="
echo ""
echo "Sports Service: http://localhost:5123"
echo "Flipper API:    http://localhost:5124"
echo ""
echo "Next steps:"
echo "  1. Register Letta tools:"
echo "     cd sports-and-media-tools/letta-tools"
echo "     python register_sports_media_tools.py"
echo ""
echo "  2. Configure agent:"
echo "     python setup_sports_agent.py"
echo ""
echo "  3. Test with your agent:"
echo "     'What games are on tonight?'"
echo "     'Watch the Patriots game'"

