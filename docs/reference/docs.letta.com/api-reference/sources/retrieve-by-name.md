# Get Source Id By Name

GET https://api.letta.com/v1/sources/name/{source_name}

Get a source by name

## Examples

```shell
curl https://api.letta.com/v1/sources/name/source_name \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.sources.retrieve_by_name(
    source_name="source_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.retrieveByName("source_name");

```

```shell
curl https://api.letta.com/v1/sources/name/:source_name \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.sources.retrieve_by_name(
    source_name="source_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.retrieveByName("source_name");

```