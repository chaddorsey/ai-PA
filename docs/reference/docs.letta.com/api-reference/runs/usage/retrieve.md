# Retrieve Usage For Run

GET https://api.letta.com/v1/runs/{run_id}/usage

Get usage statistics for a run.

## Examples

```shell
curl https://api.letta.com/v1/runs/run_id/usage \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.runs.usage.retrieve(
    run_id="run_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.usage.retrieve("run_id");

```

```shell
curl https://api.letta.com/v1/runs/:run_id/usage \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.runs.usage.retrieve(
    run_id="run_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.usage.retrieve("run_id");

```