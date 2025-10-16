# Granola Transcripts Upload Guide

This guide explains how to upload your Granola meeting transcripts to Letta's filesystem.

## Prerequisites

1. Letta service running (via Docker Compose)
2. Python 3.8+ installed
3. Required packages installed (already in `requirements.txt`)

## Quick Start

### Option 1: Run from your local machine

```bash
# Navigate to the letta directory
cd /Users/dorseyhomeserver/ai-PA/letta

# Ensure dependencies are installed
pip install -r requirements.txt

# Run the upload script
python upload_granola_transcripts.py
```

### Option 2: Run from Docker container

If you prefer to run from within a Docker container that has access to the Letta service:

```bash
# From the project root
docker-compose exec letta python /root/upload_granola_transcripts.py
```

## What the Script Does

1. **Connects to Letta**: Uses the Letta client to connect to your instance at `http://localhost:8283`
2. **Creates/Finds Folder**: Looks for a folder named `meeting_notes_and_transcripts` or creates it if it doesn't exist
3. **Uploads Files**: Iterates through all 393 .txt files in the granola-transcripts directory
4. **Progress Tracking**: Shows real-time progress, upload rate, and ETA
5. **Error Handling**: Gracefully handles failures and reports them at the end

## Expected Output

```
======================================================================
📝 Granola Transcripts Upload to Letta Filesystem
======================================================================
🔌 Connecting to Letta at http://localhost:8283
✅ Connected to Letta successfully

📁 Looking for folder 'meeting_notes_and_transcripts'...
📝 Creating new folder 'meeting_notes_and_transcripts'...
📊 Using embedding model: text-embedding-ada-002
✅ Created folder: meeting_notes_and_transcripts (ID: folder_abc123)

📊 Found 393 files to upload
📁 Source: /Users/dorseyhomeserver/ai-PA/data-resources/granola-transcripts
🎯 Target folder ID: folder_abc123

======================================================================
[1/393] 📤 Uploading: granolaNote--2025-04-16T12_00_00-04_00--f2d5b455-8f1b-4c4b-843b-8ec4958fec7b--CODAP v3 dev planning_.txt... ✅ Done
[2/393] 📤 Uploading: granolaNote--2025-04-17T13_30_00-04_00--bd3f4a5d-5ce5-4061-a05e-a8b4348a4259--Judi _ Chad.txt... ✅ Done
...
[10/393] ...
    📈 Progress: 10/393 | Rate: 2.5 files/sec | ETA: 153s
...
======================================================================

📊 Upload Summary:
   ✅ Uploaded: 393
   ❌ Failed: 0
   ⏱️  Total time: 157.3s
   📈 Average rate: 2.5 files/sec

✅ Upload process completed!
```

## Configuration

The script uses these settings (defined at the top of `upload_granola_transcripts.py`):

- **LETTA_BASE_URL**: `http://localhost:8283` (can be overridden via environment variable)
- **SOURCE_DIR**: `/Users/dorseyhomeserver/ai-PA/data-resources/granola-transcripts`
- **FOLDER_NAME**: `meeting_notes_and_transcripts`

### Customizing Settings

You can override the base URL by setting an environment variable:

```bash
export LETTA_BASE_URL="http://letta:8283"  # For Docker internal network
python upload_granola_transcripts.py
```

Or create a `.env` file in the `letta` directory:

```bash
LETTA_BASE_URL=http://localhost:8283
LETTA_API_KEY=your_api_key_if_needed
```

## Attaching to an Agent

After uploading, you can attach the folder to a Letta agent to give it access to the transcripts:

```python
from letta_client import Letta
import os

client = Letta(base_url="http://localhost:8283")

# Get your agent ID (replace with actual ID)
agent_id = os.getenv("LETTA_AGENT_ID")

# Get the folder
folders = client.folders.list()
folder = next(f for f in folders if f.name == "meeting_notes_and_transcripts")

# Attach folder to agent
client.agents.folders.attach(agent_id=agent_id, folder_id=folder.id)

print(f"✅ Folder attached to agent {agent_id}")
```

## Troubleshooting

### Connection Error

If you get a connection error:
- Ensure Letta is running: `docker-compose ps letta`
- Check the health status: `curl http://localhost:8283/v1/health/`

### Authentication Error

If you need authentication:
- Set the `LETTA_API_KEY` environment variable
- Or add it to your `.env` file

### Upload Failures

The script handles individual file failures gracefully and continues with remaining files. Check the summary at the end to see if any files failed.

### Timeout Issues

If uploads are timing out:
- Check your network connection
- Verify Letta has sufficient resources (CPU/memory)
- Consider reducing batch size (modify the script)

## Performance Notes

- **Expected Upload Rate**: 2-5 files per second (depending on file size and system)
- **Total Time for 393 files**: Approximately 2-5 minutes
- **Network**: Uses local or Docker internal network (fast)
- **Processing**: Each file is embedded using Letta's configured embedding model

## Next Steps

After upload, you can:

1. **Verify uploads** via Letta web UI at `http://localhost:8283`
2. **Attach to agents** so they can access the transcripts
3. **Search files** using Letta's file search capabilities
4. **Query content** through agent conversations

## Support

If you encounter issues:
- Check Letta logs: `docker-compose logs letta`
- Verify file permissions on source directory
- Ensure sufficient disk space
- Review the script's error messages for specific issues



