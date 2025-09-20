# List Projects (Cloud-only)

GET https://api.letta.com/v1/projects

List all projects

## Examples

```shell
curl https://api.letta.com/v1/projects \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.projects.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.projects.list();

```