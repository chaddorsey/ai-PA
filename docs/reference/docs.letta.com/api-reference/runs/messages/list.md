# List Messages For Run

GET https://api.letta.com/v1/runs/{run_id}/messages

Get response messages associated with a run.

## Examples

```shell
curl https://api.letta.com/v1/runs/run_id/messages \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.runs.messages.list(
    run_id="run_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.messages.list("run_id");

```

```shell
curl -G https://api.letta.com/v1/runs/:run_id/messages \
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
client.runs.messages.list(
    run_id="run_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.messages.list("run_id");

```