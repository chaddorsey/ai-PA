# Close All Open Files

PATCH https://api.letta.com/v1/agents/{agent_id}/files/close-all

Closes all currently open files for a given agent.

This endpoint updates the file state for the agent so that no files are marked as open.
Typically used to reset the working memory view for the agent.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/files/close-all \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.files.close_all(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.files.closeAll("agent_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/agents/:agent_id/files/close-all \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.files.close_all(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.files.closeAll("agent_id");

```