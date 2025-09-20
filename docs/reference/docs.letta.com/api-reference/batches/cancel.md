# Cancel Batch

PATCH https://api.letta.com/v1/messages/batches/{batch_id}/cancel

Cancel a batch run.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/messages/batches/batch_id/cancel \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.batches.cancel(
    batch_id="batch_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.batches.cancel("batch_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/messages/batches/:batch_id/cancel \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.batches.cancel(
    batch_id="batch_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.batches.cancel("batch_id");

```