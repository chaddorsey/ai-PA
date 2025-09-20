# Upsert Tool

PUT https://api.letta.com/v1/tools/
Content-Type: application/json

Create or update a tool

## Examples

```shell
curl -X PUT https://api.letta.com/v1/tools/ \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "source_code": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.upsert(
    source_code="source_code",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.upsert({
    sourceCode: "source_code"
});

```

```shell
curl -X PUT https://api.letta.com/v1/tools/ \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "source_code": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.upsert(
    source_code="source_code",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.upsert({
    sourceCode: "source_code"
});

```