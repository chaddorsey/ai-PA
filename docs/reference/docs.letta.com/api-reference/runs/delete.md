# Delete Run

DELETE https://api.letta.com/v1/runs/{run_id}

Delete a run by its run_id.

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/runs/run_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.runs.delete(
    run_id="run_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.delete("run_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/runs/:run_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.runs.delete(
    run_id="run_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.delete("run_id");

```