# Modify Source

PATCH https://api.letta.com/v1/sources/{source_id}
Content-Type: application/json

Update the name or documentation of an existing data source.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/sources/source_id \
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
client.sources.modify(
    source_id="source_id",
)

```

```typescript
import { LettaClient, Letta } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.modify("source_id", {});

```

```shell
curl -X PATCH https://api.letta.com/v1/sources/:source_id \
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
client.sources.modify(
    source_id="source_id",
)

```

```typescript
import { LettaClient, Letta } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.modify("source_id", {});

```