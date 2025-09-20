# Modify Block

PATCH https://api.letta.com/v1/blocks/{block_id}
Content-Type: application/json

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/blocks/block_id \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.blocks.modify(
    block_id="block_id",
)

```

```typescript
import { LettaClient, Letta } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.blocks.modify("block_id", {});

```

```shell
curl -X PATCH https://api.letta.com/v1/blocks/:block_id \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.blocks.modify(
    block_id="block_id",
)

```

```typescript
import { LettaClient, Letta } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.blocks.modify("block_id", {});

```