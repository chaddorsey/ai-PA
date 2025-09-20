# Delete Source

DELETE https://api.letta.com/v1/sources/{source_id}

Delete a data source.

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/sources/source_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.sources.delete(
    source_id="source_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.delete("source_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/sources/:source_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.sources.delete(
    source_id="source_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.delete("source_id");

```