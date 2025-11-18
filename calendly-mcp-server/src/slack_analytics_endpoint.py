#!/usr/bin/env python3
"""
Slack Analytics Export HTTP Endpoint

This provides HTTP endpoints that Letta tools can call to trigger Slack analytics exports.
Run on port 8087 (different from main MCP server on 8086).
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import os
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI(title="Slack Analytics Export Service")

SCRIPT_PATH = "/app/slack_analytics_with_dates.py"
AUTH_PATH = "/app/slack_auth_state.json"


class ExportRequest(BaseModel):
    analytics_type: str = "channels"
    days_ago: int = 3
    date_range_days: int = 1


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "slack-analytics-export"}


@app.post("/trigger-export")
async def trigger_export(request: ExportRequest):
    """Trigger a Slack analytics CSV export with custom date range."""
    
    if request.analytics_type not in ["channels", "members"]:
        raise HTTPException(status_code=400, detail="analytics_type must be 'channels' or 'members'")
    
    # Calculate dates
    end_date = datetime.now() - timedelta(days=request.days_ago)
    start_date = end_date - timedelta(days=request.date_range_days - 1)
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    try:
        result = subprocess.run(
            [
                "python", SCRIPT_PATH,
                "--type", request.analytics_type,
                "--start-date", start_str,
                "--end-date", end_str,
                "--headless",
                "--auth-file", AUTH_PATH
            ],
            capture_output=True,
            text=True,
            timeout=90
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "analytics_type": request.analytics_type,
                "date_range": {
                    "start": start_str,
                    "end": end_str
                },
                "message": f"✓ Export triggered for {start_str} to {end_str}. CSV will be in Slack Files in 1-2 minutes.",
                "stdout": result.stdout
            }
        else:
            return {
                "success": False,
                "error": result.stderr,
                "stdout": result.stdout
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8087)

