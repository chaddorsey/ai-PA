# Delete Block

DELETE https://api.letta.com/v1/blocks/{block_id}

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/blocks/block_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.blocks.delete(
    block_id="block_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.blocks.delete("block_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/blocks/:block_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.blocks.delete(
    block_id="block_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.blocks.delete("block_id");

```