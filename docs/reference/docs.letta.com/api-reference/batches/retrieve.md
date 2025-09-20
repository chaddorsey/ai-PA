# Retrieve Batch

GET https://api.letta.com/v1/messages/batches/{batch_id}

Retrieve the status and details of a batch run.

## Examples

```shell
curl https://api.letta.com/v1/messages/batches/batch_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.batches.retrieve(
    batch_id="batch_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.batches.retrieve("batch_id");

```

```shell
curl https://api.letta.com/v1/messages/batches/:batch_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.batches.retrieve(
    batch_id="batch_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.batches.retrieve("batch_id");

```