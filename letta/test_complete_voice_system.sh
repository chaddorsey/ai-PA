#!/bin/bash

echo "🎤 COMPLETE LETTA VOICE SYSTEM TEST"
echo "=================================="
echo "This will test the complete voice pipeline:"
echo "• Deepgram STT (Speech-to-Text)"
echo "• Letta AI (Natural Language Processing)" 
echo "• Cartesia TTS (Text-to-Speech)"
echo "• LiveKit (Real-time Audio Streaming)"
echo ""

# Load environment variables
if [ -f "../.env" ]; then
    echo "📁 Loading environment variables from .env..."
    export $(cat ../.env | grep -v '^#' | xargs)
else
    echo "❌ .env file not found in parent directory"
    exit 1
fi

# Check required environment variables
required_vars=("LETTA_AGENT_ID" "LETTA_BASE_URL" "LIVEKIT_URL" "LIVEKIT_API_KEY" "LIVEKIT_API_SECRET" "DEEPGRAM_API_KEY" "CARTESIA_API_KEY")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Missing environment variable: $var"
        exit 1
    fi
done

echo "✅ All environment variables are set"
echo ""

# Start the voice agent
echo "🚀 Starting proper Cartesia voice agent..."
echo "Room: proper-cartesia-test"
echo ""

# Start the agent in the background
arch -arm64 python3 proper_cartesia_agent.py connect --room proper-cartesia-test &
AGENT_PID=$!

echo "⏳ Waiting for agent to start..."
sleep 5

# Check if agent is running
if ps -p $AGENT_PID > /dev/null; then
    echo "✅ Voice agent is running (PID: $AGENT_PID)"
else
    echo "❌ Voice agent failed to start"
    exit 1
fi

echo ""
echo "🌐 Starting HTTP server for voice client..."
arch -arm64 python3 serve_voice_client.py &
SERVER_PID=$!

echo "⏳ Waiting for server to start..."
sleep 3

echo ""
echo "🎧 VOICE SYSTEM READY!"
echo "======================"
echo "✅ Voice agent is running with Cartesia TTS"
echo "✅ HTTP server is running"
echo ""
echo "📱 Open your browser and go to:"
echo "   http://localhost:8088/voice_client_proper.html"
echo ""
echo "🎤 Instructions:"
echo "1. Click 'Connect to Agent' in the browser"
echo "2. Click 'Enable Microphone' when prompted"
echo "3. Speak into your microphone"
echo "4. You should hear the agent respond through your speakers"
echo ""
echo "Press Ctrl+C to stop both services"

# Wait for user interrupt
trap 'echo ""; echo "🛑 Stopping services..."; kill $AGENT_PID $SERVER_PID 2>/dev/null; echo "✅ Services stopped"; exit 0' INT

# Keep script running
wait
