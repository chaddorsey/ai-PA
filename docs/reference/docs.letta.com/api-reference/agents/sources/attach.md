# Attach Source

PATCH https://api.letta.com/v1/agents/{agent_id}/sources/attach/{source_id}

Attach a source to an agent.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/sources/attach/source_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.sources.attach(
    agent_id="agent_id",
    source_id="source_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.sources.attach("agent_id", "source_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/agents/:agent_id/sources/attach/:source_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.sources.attach(
    agent_id="agent_id",
    source_id="source_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.sources.attach("agent_id", "source_id");

```