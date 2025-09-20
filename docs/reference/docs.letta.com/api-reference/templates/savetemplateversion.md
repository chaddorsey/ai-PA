# Save template version (Cloud-only)

POST https://api.letta.com/v1/templates/{project}/{template_name}
Content-Type: application/json

Saves the current version of the template as a new version

## Examples

```shell
curl -X POST https://api.letta.com/v1/templates/project/template_name \
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
client.templates.savetemplateversion(
    project="project",
    template_name="template_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.savetemplateversion("project", "template_name");

```

```shell
curl -X POST https://api.letta.com/v1/templates/:project/:template_name \
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
client.templates.savetemplateversion(
    project="project",
    template_name="template_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.savetemplateversion("project", "template_name");

```