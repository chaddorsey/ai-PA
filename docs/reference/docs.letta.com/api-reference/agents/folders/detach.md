# Detach Folder From Agent

PATCH https://api.letta.com/v1/agents/{agent_id}/folders/detach/{folder_id}

Detach a folder from an agent.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/folders/detach/folder_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.folders.detach(
    agent_id="agent_id",
    folder_id="folder_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.folders.detach("agent_id", "folder_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/agents/:agent_id/folders/detach/:folder_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.folders.detach(
    agent_id="agent_id",
    folder_id="folder_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.folders.detach("agent_id", "folder_id");

```