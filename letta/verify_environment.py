#!/usr/bin/env python3
"""
Verify environment variables for scheduling orchestrator tool.

Checks that all required environment variables are set correctly.
Loads from .env file if present.
"""

import os
import sys
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    # Load from project root .env file
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded environment variables from {env_path}\n")
except ImportError:
    pass  # python-dotenv not installed, skip
except Exception as e:
    print(f"⚠ Could not load .env file: {e}\n")

def check_env_var(name, required=True, mask=True):
    """Check if an environment variable is set."""
    value = os.getenv(name)
    if value:
        if mask and any(keyword in name.upper() for keyword in ['KEY', 'SECRET', 'TOKEN', 'PASSWORD']):
            # Mask sensitive values
            display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
        else:
            display_value = value
        print(f"  ✓ {name}: {display_value}")
        return True
    else:
        if required:
            print(f"  ✗ {name}: NOT SET (required)")
        else:
            print(f"  ⚠ {name}: NOT SET (optional)")
        return False

def main():
    """Verify environment variables."""
    
    print(f"{'='*60}")
    print("Environment Variables Verification")
    print(f"{'='*60}\n")
    
    all_ok = True
    
    # LLM API Keys (at least one required)
    print("LLM API Keys (at least one required):")
    has_openai = check_env_var("OPENAI_API_KEY", required=False)
    has_anthropic = check_env_var("ANTHROPIC_API_KEY", required=False)
    
    if not has_openai and not has_anthropic:
        print("  ❌ No LLM API key found! DSPy extraction will fail.")
        print("     Set either OPENAI_API_KEY or ANTHROPIC_API_KEY")
        all_ok = False
    else:
        print("  ✓ At least one LLM API key is set")
    
    print()
    
    # Letta Configuration
    print("Letta Configuration:")
    check_env_var("LETTA_BASE_URL", required=False)
    has_agent_id = check_env_var("LETTA_AGENT_ID", required=False)
    
    print()
    
    # Summary
    print(f"{'='*60}")
    if all_ok and (has_openai or has_anthropic):
        print("✓ Environment variables are properly configured")
        if not has_agent_id:
            print("\n⚠ Note: LETTA_AGENT_ID is not set.")
            print("  This is only needed for attaching tools to agents.")
            print("  You can still register tools without it.")
        return 0
    else:
        print("❌ Some required environment variables are missing")
        print("\nTo set environment variables:")
        print("  export OPENAI_API_KEY='your-key'")
        print("  export LETTA_BASE_URL='http://localhost:8283'")
        print("  export LETTA_AGENT_ID='your-agent-id'")
        return 1

if __name__ == "__main__":
    sys.exit(main())

