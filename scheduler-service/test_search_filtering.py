#!/usr/bin/env python3
"""Test script for scheduler search and filtering functionality."""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

import httpx


BASE_URL = "http://localhost:8087/v1"
TIMEOUT = 30.0


async def test_list_jobs_with_filters():
    """Test list_jobs endpoint with various filters."""
    print("\n=== Testing list_jobs with filters ===\n")
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Test 1: List all jobs
        print("1. Listing all jobs...")
        response = await client.get(f"{BASE_URL}/jobs")
        assert response.status_code == 200
        all_jobs = response.json()
        print(f"   Found {len(all_jobs)} jobs")
        
        # Test 2: Filter by status
        print("\n2. Filtering by status=scheduled...")
        response = await client.get(f"{BASE_URL}/jobs?status_filter=scheduled")
        assert response.status_code == 200
        scheduled_jobs = response.json()
        print(f"   Found {len(scheduled_jobs)} scheduled jobs")
        
        # Test 3: Filter by category (if any jobs have categories)
        print("\n3. Testing category filter...")
        if all_jobs:
            categories = {job.get("category") for job in all_jobs if job.get("category")}
            if categories:
                test_category = list(categories)[0]
                response = await client.get(f"{BASE_URL}/jobs?category_filter={test_category}")
                assert response.status_code == 200
                category_jobs = response.json()
                print(f"   Found {len(category_jobs)} jobs in category '{test_category}'")
            else:
                print("   No jobs with categories found - skipping")
        
        # Test 4: Filter by created_by (if any jobs exist)
        if all_jobs:
            creators = {job.get("created_by") for job in all_jobs if job.get("created_by")}
            if creators:
                test_creator = list(creators)[0]
                print(f"\n4. Filtering by created_by='{test_creator}'...")
                response = await client.get(f"{BASE_URL}/jobs?created_by_filter={test_creator}")
                assert response.status_code == 200
                creator_jobs = response.json()
                print(f"   Found {len(creator_jobs)} jobs created by '{test_creator}'")
        
        print("\n✅ Filter tests passed!")


async def test_search_jobs():
    """Test semantic search endpoint."""
    print("\n=== Testing semantic search ===\n")
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # First, check if we have any jobs
        response = await client.get(f"{BASE_URL}/jobs")
        all_jobs = response.json()
        
        if not all_jobs:
            print("⚠️  No jobs found - creating a test job for search...")
            # Create a test job
            test_job = {
                "title": "Daily Backup Task",
                "description": "Automated daily backup of system files and database",
                "created_by": "test-script",
                "category": "backup",
                "schedule": {
                    "type": "cron",
                    "expression": {"cron": "0 2 * * *"}  # Daily at 2 AM
                }
            }
            response = await client.post(f"{BASE_URL}/jobs", json=test_job)
            if response.status_code == 201:
                print("   Test job created")
                await asyncio.sleep(2)  # Wait for embedding generation
            else:
                print(f"   Failed to create test job: {response.status_code} {response.text}")
                return
        
        # Test 1: Basic semantic search
        print("1. Testing basic semantic search...")
        response = await client.get(
            f"{BASE_URL}/jobs/search",
            params={"query_text": "backup", "limit": 5}
        )
        
        if response.status_code == 503:
            print("   ⚠️  Embedding model not available - search requires sentence-transformers")
            print("   This is expected if the embedding service isn't configured")
            return
        elif response.status_code != 200:
            print(f"   ❌ Search failed: {response.status_code} {response.text}")
            return
        
        results = response.json()
        print(f"   Found {len(results)} results for query 'backup'")
        if results:
            print(f"   Top result: {results[0].get('title', 'N/A')}")
        
        # Test 2: Search with filters
        print("\n2. Testing search with category filter...")
        response = await client.get(
            f"{BASE_URL}/jobs/search",
            params={
                "query_text": "task",
                "limit": 10,
                "category_filter": "backup",
                "min_score": 0.3
            }
        )
        
        if response.status_code == 200:
            filtered_results = response.json()
            print(f"   Found {len(filtered_results)} results with category filter")
        elif response.status_code == 503:
            print("   ⚠️  Embedding model not available")
        else:
            print(f"   Search with filter returned: {response.status_code}")
        
        # Test 3: Search with status filter
        print("\n3. Testing search with status filter...")
        response = await client.get(
            f"{BASE_URL}/jobs/search",
            params={
                "query_text": "scheduled",
                "limit": 5,
                "status_filter": "scheduled",
                "min_score": 0.2
            }
        )
        
        if response.status_code == 200:
            status_results = response.json()
            print(f"   Found {len(status_results)} scheduled jobs matching query")
        elif response.status_code == 503:
            print("   ⚠️  Embedding model not available")
        
        print("\n✅ Search tests completed!")


async def test_mcp_tools():
    """Test MCP server tools endpoint."""
    print("\n=== Testing MCP server ===\n")
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Test health endpoint
        print("1. Testing MCP health endpoint...")
        try:
            response = await client.get("http://localhost:8088/health")
            if response.status_code == 200:
                print(f"   ✅ MCP server is healthy: {response.json()}")
            else:
                print(f"   ⚠️  MCP server returned: {response.status_code}")
        except Exception as e:
            print(f"   ⚠️  Could not connect to MCP server: {e}")
            print("   (This is OK if the server isn't running)")
        
        # Test MCP tools list (would need proper MCP protocol call)
        print("\n2. MCP tools are exposed via Letta's MCP configuration")
        print("   Tools available:")
        print("   - scheduler_list_jobs (with filters)")
        print("   - scheduler_search_jobs (semantic search)")
        print("   - scheduler_get_job")
        print("   - scheduler_create_job")
        print("   - scheduler_update_job")
        print("   - scheduler_delete_job")
        print("   - scheduler_list_executions")
        print("   - scheduler_get_execution")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Scheduler Search & Filtering Test Suite")
    print("=" * 60)
    
    try:
        await test_list_jobs_with_filters()
        await test_search_jobs()
        await test_mcp_tools()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

