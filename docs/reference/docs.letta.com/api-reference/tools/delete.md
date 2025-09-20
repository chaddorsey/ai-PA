# Delete Tool

DELETE https://api.letta.com/v1/tools/{tool_id}

Delete a tool by name

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/tools/tool_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.delete(
    tool_id="tool_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.delete("tool_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/tools/:tool_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.delete(
    tool_id="tool_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.delete("tool_id");

```