# Add Composio Tool

POST https://api.letta.com/v1/tools/composio/{composio_action_name}

Add a new Composio tool by action name (Composio refers to each tool as an `Action`)

## Examples

```shell
curl -X POST https://api.letta.com/v1/tools/composio/composio_action_name \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.add_composio_tool(
    composio_action_name="composio_action_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.addComposioTool("composio_action_name");

```

```shell
curl -X POST https://api.letta.com/v1/tools/composio/:composio_action_name \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.add_composio_tool(
    composio_action_name="composio_action_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.addComposioTool("composio_action_name");

```