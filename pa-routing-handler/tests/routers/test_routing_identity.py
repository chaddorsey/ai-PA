"""Tests for identity resolution in routing."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestResolveIdentity:
    """Tests for resolve_identity function."""

    @pytest.fixture
    def sample_identities(self):
        """Sample identity data matching Letta API response format."""
        return [
            {
                "id": "identity-dan-123",
                "identifier_key": "ddamelin@concord.org",
                "name": "Dan Damelin",
                "properties": [
                    {"key": "slack_id", "value": "U0303SG91", "type": "string"},
                    {"key": "email", "value": "ddamelin@concord.org", "type": "string"},
                ]
            },
            {
                "id": "identity-chad-456",
                "identifier_key": "cdorsey@concord.org",
                "name": "Chad Dorsey",
                "properties": [
                    {"key": "telegram_id", "value": "123456789", "type": "string"},
                    {"key": "slack_id", "value": "U02V82YB9", "type": "string"},
                ]
            }
        ]

    @pytest.mark.asyncio
    async def test_resolve_identity_with_platform_found(self, sample_identities):
        """Resolves identity when platform/platform_id matches a property."""
        from pa_routing.routers.routing import resolve_identity, invalidate_identities_cache

        # Reset cache
        invalidate_identities_cache()

        with patch("pa_routing.routers.routing._fetch_identities", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_identities

            result = await resolve_identity(
                platform="telegram",
                platform_id="123456789",
                default_identity_id=None
            )

            assert result == "identity-chad-456"
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_identity_with_platform_not_found(self, sample_identities):
        """Falls back to default when platform/platform_id doesn't match."""
        from pa_routing.routers.routing import resolve_identity, invalidate_identities_cache

        invalidate_identities_cache()

        with patch("pa_routing.routers.routing._fetch_identities", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_identities

            result = await resolve_identity(
                platform="telegram",
                platform_id="unknown-user",
                default_identity_id="identity-default-789"
            )

            assert result == "identity-default-789"

    @pytest.mark.asyncio
    async def test_resolve_identity_default_fallback(self):
        """Falls back to default_identity_id when no platform provided."""
        from pa_routing.routers.routing import resolve_identity

        result = await resolve_identity(
            platform=None,
            platform_id=None,
            default_identity_id="identity-default-123"
        )

        assert result == "identity-default-123"

    @pytest.mark.asyncio
    async def test_resolve_identity_no_platform_no_default(self):
        """Returns None when no platform and no default."""
        from pa_routing.routers.routing import resolve_identity

        result = await resolve_identity(
            platform=None,
            platform_id=None,
            default_identity_id=None
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_identity_platform_without_id(self):
        """Falls back to default when platform provided but no platform_id."""
        from pa_routing.routers.routing import resolve_identity

        result = await resolve_identity(
            platform="slack",
            platform_id=None,
            default_identity_id="identity-default-123"
        )

        assert result == "identity-default-123"

    @pytest.mark.asyncio
    async def test_resolve_identity_slack_lookup(self, sample_identities):
        """Resolves identity via slack_id property."""
        from pa_routing.routers.routing import resolve_identity, invalidate_identities_cache

        invalidate_identities_cache()

        with patch("pa_routing.routers.routing._fetch_identities", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_identities

            result = await resolve_identity(
                platform="slack",
                platform_id="U0303SG91",
                default_identity_id=None
            )

            assert result == "identity-dan-123"


class TestFetchIdentities:
    """Tests for _fetch_identities caching behavior."""

    @pytest.mark.asyncio
    async def test_fetch_identities_caches_result(self):
        """Caches identities after first fetch."""
        from pa_routing.routers.routing import _fetch_identities, invalidate_identities_cache

        invalidate_identities_cache()

        mock_response = MagicMock()
        mock_response.json.return_value = [{"id": "test-1"}]
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_async_client = AsyncMock()
            mock_async_client.get.return_value = mock_response
            mock_async_client.__aenter__.return_value = mock_async_client
            mock_async_client.__aexit__.return_value = None
            mock_client.return_value = mock_async_client

            # First call - should fetch
            result1 = await _fetch_identities()
            assert result1 == [{"id": "test-1"}]

            # Second call - should use cache
            result2 = await _fetch_identities()
            assert result2 == [{"id": "test-1"}]

            # Only one HTTP call should be made
            assert mock_async_client.get.call_count == 1

    def test_invalidate_cache_clears_cache(self):
        """invalidate_identities_cache clears the cache."""
        from pa_routing.routers import routing

        # Set cache directly for testing
        routing._identities_cache = [{"id": "cached"}]

        routing.invalidate_identities_cache()

        assert routing._identities_cache is None
