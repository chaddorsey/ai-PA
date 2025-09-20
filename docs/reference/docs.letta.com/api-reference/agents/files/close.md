# Close File

PATCH https://api.letta.com/v1/agents/{agent_id}/files/{file_id}/close

Closes a specific file for a given agent.

This endpoint marks a specific file as closed in the agent's file state.
The file will be removed from the agent's working memory view.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/files/file_id/close \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.files.close(
    agent_id="agent_id",
    file_id="file_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.files.close("agent_id", "file_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/agents/:agent_id/files/:file_id/close \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.files.close(
    agent_id="agent_id",
    file_id="file_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.files.close("agent_id", "file_id");

```