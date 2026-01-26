"""
Pytest configuration for pa-routing-handler tests.

Sets up test environment variables before any imports.
"""

import os

# Set test database URL before any module imports
# This prevents SQLAlchemy from failing on empty URL
# Field name is postgres_url with PA_ROUTING_ prefix
os.environ.setdefault(
    "PA_ROUTING_POSTGRES_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test"
)

# Set a test default identity ID
os.environ.setdefault(
    "PA_ROUTING_DEFAULT_IDENTITY_ID",
    "identity-test-default"
)

# Set Letta base URL for tests
os.environ.setdefault(
    "PA_ROUTING_LETTA_BASE_URL",
    "http://localhost:8283"
)
