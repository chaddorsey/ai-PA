# List Passages

GET https://api.letta.com/v1/agents/{agent_id}/archival-memory

Retrieve the memories in an agent's archival memory store (paginated query).

## Examples

```shell
curl https://api.letta.com/v1/agents/agent_id/archival-memory \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.passages.list(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.passages.list("agent_id");

```

```shell
curl -G https://api.letta.com/v1/agents/:agent_id/archival-memory \
     -H "Authorization: Bearer <token>" \
     -d after=string \
     -d before=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.passages.list(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.passages.list("agent_id");

```