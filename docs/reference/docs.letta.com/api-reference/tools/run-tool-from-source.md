# Run Tool From Source

POST https://api.letta.com/v1/tools/run
Content-Type: application/json

Attempt to build a tool from source, then run it on the provided arguments

## Examples

```shell
curl -X POST https://api.letta.com/v1/tools/run \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "source_code": "string",
  "args": {}
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.run_tool_from_source(
    source_code="source_code",
    args={"key": "value"},
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.runToolFromSource({
    sourceCode: "source_code",
    args: {
        "key": "value"
    }
});

```

```shell
curl -X POST https://api.letta.com/v1/tools/run \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "source_code": "string",
  "args": {
    "string": {}
  }
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.run_tool_from_source(
    source_code="source_code",
    args={"key": "value"},
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.runToolFromSource({
    sourceCode: "source_code",
    args: {
        "key": "value"
    }
});

```