# Count Tools

GET https://api.letta.com/v1/tools/count

Get a count of all tools available to agents belonging to the org of the user.

## Examples

```shell
curl https://api.letta.com/v1/tools/count \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.count()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.count();

```

```shell
curl -G https://api.letta.com/v1/tools/count \
     -H "Authorization: Bearer <token>" \
     -d name=string \
     -d names=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.count()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.count();

```