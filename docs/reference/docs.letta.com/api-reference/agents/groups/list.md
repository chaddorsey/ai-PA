# List Agent Groups

GET https://api.letta.com/v1/agents/{agent_id}/groups

Lists the groups for an agent

## Examples

```shell
curl https://api.letta.com/v1/agents/agent_id/groups \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.groups.list(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.groups.list("agent_id");

```

```shell
curl -G https://api.letta.com/v1/agents/:agent_id/groups \
     -H "Authorization: Bearer <token>" \
     -d manager_type=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.groups.list(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.groups.list("agent_id");

```