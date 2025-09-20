# Upsert Base Tools

POST https://api.letta.com/v1/tools/add-base-tools

Upsert base tools

## Examples

```shell
curl -X POST https://api.letta.com/v1/tools/add-base-tools \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.upsert_base_tools()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.upsertBaseTools();

```

```shell
curl -X POST https://api.letta.com/v1/tools/add-base-tools \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.upsert_base_tools()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.upsertBaseTools();

```