# Modify Tool

PATCH https://api.letta.com/v1/tools/{tool_id}
Content-Type: application/json

Update an existing tool

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/tools/tool_id \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.modify(
    tool_id="tool_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.modify("tool_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/tools/:tool_id \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.modify(
    tool_id="tool_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.modify("tool_id");

```