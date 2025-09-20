# Fork template (Cloud-only)

POST https://api.letta.com/v1/templates/{project}/{template_version}/fork
Content-Type: application/json

Forks a template version into a new template

## Examples

```shell
curl -X POST https://api.letta.com/v1/templates/project/template_version/fork \
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
client.templates.forktemplate(
    project="project",
    template_version="template_version",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.forktemplate("project", "template_version");

```

```shell
curl -X POST https://api.letta.com/v1/templates/:project/:template_version/fork \
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
client.templates.forktemplate(
    project="project",
    template_version="template_version",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.forktemplate("project", "template_version");

```