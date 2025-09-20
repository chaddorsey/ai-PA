# Create Block

POST https://api.letta.com/v1/blocks/
Content-Type: application/json

## Examples

```shell
curl -X POST https://api.letta.com/v1/blocks/ \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "value": "string",
  "label": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.blocks.create(
    value="value",
    label="label",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.blocks.create({
    value: "value",
    label: "label"
});

```

```shell
curl -X POST https://api.letta.com/v1/blocks/ \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "value": "string",
  "label": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.blocks.create(
    value="value",
    label="label",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.blocks.create({
    value: "value",
    label: "label"
});

```