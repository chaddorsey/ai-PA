# List Composio Actions By App

GET https://api.letta.com/v1/tools/composio/apps/{composio_app_name}/actions

Get a list of all Composio actions for a specific app

## Examples

```shell
curl https://api.letta.com/v1/tools/composio/apps/composio_app_name/actions \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.list_composio_actions_by_app(
    composio_app_name="composio_app_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.listComposioActionsByApp("composio_app_name");

```

```shell
curl https://api.letta.com/v1/tools/composio/apps/:composio_app_name/actions \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.list_composio_actions_by_app(
    composio_app_name="composio_app_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.listComposioActionsByApp("composio_app_name");

```