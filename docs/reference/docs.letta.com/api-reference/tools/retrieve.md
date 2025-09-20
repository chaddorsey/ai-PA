# Retrieve Tool

GET https://api.letta.com/v1/tools/{tool_id}

Get a tool by ID

## Examples

```shell
curl https://api.letta.com/v1/tools/tool_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.retrieve(
    tool_id="tool_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.retrieve("tool_id");

```

```shell
curl https://api.letta.com/v1/tools/:tool_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.retrieve(
    tool_id="tool_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.retrieve("tool_id");

```