# Detach Tool

PATCH https://api.letta.com/v1/agents/{agent_id}/tools/detach/{tool_id}

Detach a tool from an agent.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/tools/detach/tool_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.tools.detach(
    agent_id="agent_id",
    tool_id="tool_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.tools.detach("agent_id", "tool_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/agents/:agent_id/tools/detach/:tool_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.tools.detach(
    agent_id="agent_id",
    tool_id="tool_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.tools.detach("agent_id", "tool_id");

```