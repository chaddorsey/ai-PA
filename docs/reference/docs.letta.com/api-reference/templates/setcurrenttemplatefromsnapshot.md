# Set current template from snapshot (Cloud-only)

PUT https://api.letta.com/v1/templates/{project}/{template_version}/snapshot
Content-Type: application/json

Updates the current working version of a template from a snapshot

## Examples

```shell
curl -X PUT https://api.letta.com/v1/templates/project/template_version/snapshot \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.setcurrenttemplatefromsnapshot(
    project="project",
    template_version="template_version",
    request={"key": "value"},
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.setcurrenttemplatefromsnapshot("project", "template_version", {
    "key": "value"
});

```

```shell
curl -X PUT https://api.letta.com/v1/templates/:project/:template_version/snapshot \
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
client.templates.setcurrenttemplatefromsnapshot(
    project="project",
    template_version="template_version",
    request={"key": "value"},
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.setcurrenttemplatefromsnapshot("project", "template_version", {
    "key": "value"
});

```

```shell
curl -X PUT https://api.letta.com/v1/templates/:project/:template_version/snapshot \
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
client.templates.setcurrenttemplatefromsnapshot(
    project="project",
    template_version="template_version",
    request={"key": "value"},
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.setcurrenttemplatefromsnapshot("project", "template_version", {
    "key": "value"
});

```

```shell
curl -X PUT https://api.letta.com/v1/templates/:project/:template_version/snapshot \
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
client.templates.setcurrenttemplatefromsnapshot(
    project="project",
    template_version="template_version",
    request={"key": "value"},
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.setcurrenttemplatefromsnapshot("project", "template_version", {
    "key": "value"
});

```