# List Runs

GET https://api.letta.com/v1/runs/

List all runs.

## Examples

```shell
curl https://api.letta.com/v1/runs/ \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.runs.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.list();

```

```shell
curl -G https://api.letta.com/v1/runs/ \
     -H "Authorization: Bearer <token>" \
     -d agent_id=string \
     -d agent_ids=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.runs.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.list();

```