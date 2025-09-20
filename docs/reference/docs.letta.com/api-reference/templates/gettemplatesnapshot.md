# Get template snapshot (Cloud-only)

GET https://api.letta.com/v1/templates/{project}/{template_version}/snapshot

Get a snapshot of the template version, this will return the template state at a specific version

## Examples

```shell
curl https://api.letta.com/v1/templates/project/template_version/snapshot \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.gettemplatesnapshot(
    project="project",
    template_version="template_version",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.gettemplatesnapshot("project", "template_version");

```