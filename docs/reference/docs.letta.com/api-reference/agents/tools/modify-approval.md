# Modify Approval

PATCH https://api.letta.com/v1/agents/{agent_id}/tools/approval/{tool_name}

Attach a tool to an agent.

## Examples

```shell
curl -X PATCH "https://api.letta.com/v1/agents/agent_id/tools/approval/tool_name?requires_approval=true" \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.tools.modify_approval(
    agent_id="agent_id",
    tool_name="tool_name",
    requires_approval=True,
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.tools.modifyApproval("agent_id", "tool_name", {
    requiresApproval: true
});

```

```shell
curl -X PATCH "https://api.letta.com/v1/agents/:agent_id/tools/approval/:tool_name?requires_approval=true" \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.tools.modify_approval(
    agent_id="agent_id",
    tool_name="tool_name",
    requires_approval=True,
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.tools.modifyApproval("agent_id", "tool_name", {
    requiresApproval: true
});

```