# List Messages For Batch

GET https://api.letta.com/v1/messages/batches/{batch_id}/messages

Get response messages for a specific batch job.

## Examples

```shell
curl https://api.letta.com/v1/messages/batches/batch_id/messages \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.batches.messages.list(
    batch_id="batch_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.batches.messages.list("batch_id");

```

```shell
curl -G https://api.letta.com/v1/messages/batches/:batch_id/messages \
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
client.batches.messages.list(
    batch_id="batch_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.batches.messages.list("batch_id");

```