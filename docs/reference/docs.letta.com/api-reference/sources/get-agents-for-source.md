# Get Agents For Source

GET https://api.letta.com/v1/sources/{source_id}/agents

Get all agent IDs that have the specified source attached.

## Examples

```shell
curl https://api.letta.com/v1/sources/source_id/agents \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.sources.get_agents_for_source(
    source_id="source_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.getAgentsForSource("source_id");

```

```shell
curl https://api.letta.com/v1/sources/:source_id/agents \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.sources.get_agents_for_source(
    source_id="source_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.getAgentsForSource("source_id");

```