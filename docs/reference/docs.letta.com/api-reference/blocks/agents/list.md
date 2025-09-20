# List Agents For Block

GET https://api.letta.com/v1/blocks/{block_id}/agents

Retrieves all agents associated with the specified block.
Raises a 404 if the block does not exist.

## Examples

```shell
curl https://api.letta.com/v1/blocks/block_id/agents \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.blocks.agents.list(
    block_id="block_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.blocks.agents.list("block_id");

```

```shell
curl -G https://api.letta.com/v1/blocks/:block_id/agents \
     -H "Authorization: Bearer <token>" \
     -d before=string \
     -d after=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.blocks.agents.list(
    block_id="block_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.blocks.agents.list("block_id");

```