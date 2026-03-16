"""Register manage_widget_queue tool with Letta and attach to Rover."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from letta_client import Letta

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
ROVER_AGENT_ID = "agent-76ee5448-68ec-4fdd-b102-d4895d44e090"

client = Letta(base_url=LETTA_BASE_URL)

# Register tool
from widget_queue_tool import manage_widget_queue
tool = client.tools.upsert_from_function(func=manage_widget_queue)
print(f"Registered tool: {tool.name} (id: {tool.id})")

# Get Rover's current tools and add this one
agent = client.agents.retrieve(agent_id=ROVER_AGENT_ID)
current_tool_ids = [t.id for t in agent.tools]
if tool.id not in current_tool_ids:
    current_tool_ids.append(tool.id)
    client.agents.modify(agent_id=ROVER_AGENT_ID, tool_ids=current_tool_ids)
    print(f"Attached to Rover ({ROVER_AGENT_ID})")
else:
    print(f"Already attached to Rover")
