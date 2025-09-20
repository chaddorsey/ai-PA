# Search Messages

POST https://api.letta.com/v1/agents/messages/search
Content-Type: application/json

Search messages across the entire organization with optional project and template filtering. Returns messages with FTS/vector ranks and total RRF score.

This is a cloud-only feature.

## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/messages/search \
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
client.agents.messages.search()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.search();

```

```shell
curl -X POST https://api.letta.com/v1/agents/messages/search \
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
client.agents.messages.search()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.search();

```