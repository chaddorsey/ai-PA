# Update template description (Cloud-only)

PATCH https://api.letta.com/v1/templates/{project}/{template_name}/description
Content-Type: application/json

Updates the description for all versions of a template with the specified name. Versions are automatically stripped from the current template name if accidentally included.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/templates/project/template_name/description \
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
client.templates.updatetemplatedescription(
    project="project",
    template_name="template_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.updatetemplatedescription("project", "template_name");

```

```shell
curl -X PATCH https://api.letta.com/v1/templates/:project/:template_name/description \
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
client.templates.updatetemplatedescription(
    project="project",
    template_name="template_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.updatetemplatedescription("project", "template_name");

```

```shell
curl -X PATCH https://api.letta.com/v1/templates/:project/:template_name/description \
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
client.templates.updatetemplatedescription(
    project="project",
    template_name="template_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.updatetemplatedescription("project", "template_name");

```