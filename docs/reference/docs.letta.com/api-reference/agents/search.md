# Search Agents

POST https://api.letta.com/v1/agents/search
Content-Type: application/json

<Note>This endpoint is only available on Letta Cloud.</Note>

Search deployed agents.


## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/search \
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
client.agents.search()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.search();

```