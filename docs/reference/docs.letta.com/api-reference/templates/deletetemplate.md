# Delete template (Cloud-only)

DELETE https://api.letta.com/v1/templates/{project}/{template_name}
Content-Type: application/json

Deletes all versions of a template with the specified name

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/templates/project/template_name \
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
client.templates.deletetemplate(
    project="project",
    template_name="template_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.deletetemplate("project", "template_name");

```

```shell
curl -X DELETE https://api.letta.com/v1/templates/:project/:template_name \
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
client.templates.deletetemplate(
    project="project",
    template_name="template_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.deletetemplate("project", "template_name");

```