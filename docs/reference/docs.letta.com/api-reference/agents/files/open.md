# Open File

PATCH https://api.letta.com/v1/agents/{agent_id}/files/{file_id}/open

Opens a specific file for a given agent.

This endpoint marks a specific file as open in the agent's file state.
The file will be included in the agent's working memory view.
Returns a list of file names that were closed due to LRU eviction.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/files/file_id/open \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.files.open(
    agent_id="agent_id",
    file_id="file_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.files.open("agent_id", "file_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/agents/:agent_id/files/:file_id/open \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.files.open(
    agent_id="agent_id",
    file_id="file_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.files.open("agent_id", "file_id");

```