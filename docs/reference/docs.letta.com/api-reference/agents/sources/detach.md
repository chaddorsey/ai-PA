# Detach Source

PATCH https://api.letta.com/v1/agents/{agent_id}/sources/detach/{source_id}

Detach a source from an agent.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/sources/detach/source_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.sources.detach(
    agent_id="agent_id",
    source_id="source_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.sources.detach("agent_id", "source_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/agents/:agent_id/sources/detach/:source_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.sources.detach(
    agent_id="agent_id",
    source_id="source_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.sources.detach("agent_id", "source_id");

```