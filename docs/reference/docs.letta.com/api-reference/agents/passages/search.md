# Search Archival Memory

GET https://api.letta.com/v1/agents/{agent_id}/archival-memory/search

Search archival memory using semantic (embedding-based) search with optional temporal filtering.

This endpoint allows manual triggering of archival memory searches, enabling users to query
an agent's archival memory store directly via the API. The search uses the same functionality
as the agent's archival_memory_search tool but is accessible for external API usage.

## Examples

```shell
curl -G https://api.letta.com/v1/agents/agent_id/archival-memory/search \
     -H "Authorization: Bearer <token>" \
     -d query=query
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.passages.search(
    agent_id="agent_id",
    query="query",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.passages.search("agent_id", {
    query: "query"
});

```

```shell
curl -G https://api.letta.com/v1/agents/:agent_id/archival-memory/search \
     -H "Authorization: Bearer <token>" \
     -d query=string \
     -d tags=string \
     -d tag_match_mode=any
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.passages.search(
    agent_id="agent_id",
    query="query",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.passages.search("agent_id", {
    query: "query"
});

```