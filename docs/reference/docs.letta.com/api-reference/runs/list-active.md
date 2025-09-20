# List Active Runs

GET https://api.letta.com/v1/runs/active

List all active runs.

## Examples

```shell
curl https://api.letta.com/v1/runs/active \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.runs.list_active()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.listActive();

```

```shell
curl -G https://api.letta.com/v1/runs/active \
     -H "Authorization: Bearer <token>" \
     -d agent_id=string \
     -d background=true
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.runs.list_active()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.listActive();

```