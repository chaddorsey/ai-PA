# Rename template (Cloud-only)

PATCH https://api.letta.com/v1/templates/{project}/{template_name}/name
Content-Type: application/json

Renames all versions of a template with the specified name. Versions are automatically stripped from the current template name if accidentally included.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/templates/project/template_name/name \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "new_name": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.renametemplate(
    project="project",
    template_name="template_name",
    new_name="new_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.renametemplate("project", "template_name", {
    newName: "new_name"
});

```

```shell
curl -X PATCH https://api.letta.com/v1/templates/:project/:template_name/name \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "new_name": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.renametemplate(
    project="project",
    template_name="template_name",
    new_name="new_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.renametemplate("project", "template_name", {
    newName: "new_name"
});

```

```shell
curl -X PATCH https://api.letta.com/v1/templates/:project/:template_name/name \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "new_name": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.renametemplate(
    project="project",
    template_name="template_name",
    new_name="new_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.renametemplate("project", "template_name", {
    newName: "new_name"
});

```

```shell
curl -X PATCH https://api.letta.com/v1/templates/:project/:template_name/name \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "new_name": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.renametemplate(
    project="project",
    template_name="template_name",
    new_name="new_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.renametemplate("project", "template_name", {
    newName: "new_name"
});

```