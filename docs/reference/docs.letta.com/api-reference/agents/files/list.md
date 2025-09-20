# List Agent Files

GET https://api.letta.com/v1/agents/{agent_id}/files

Get the files attached to an agent with their open/closed status (paginated).

## Examples

```shell
curl https://api.letta.com/v1/agents/agent_id/files \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.files.list(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.files.list("agent_id");

```

```shell
curl -G https://api.letta.com/v1/agents/:agent_id/files \
     -H "Authorization: Bearer <token>" \
     -d cursor=string \
     -d limit=0
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.files.list(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.files.list("agent_id");

```