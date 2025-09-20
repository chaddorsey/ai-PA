# List template versions (Cloud-only)

GET https://api.letta.com/v1/templates/{project_slug}/{name}/versions

List all versions of a specific template

## Examples

```shell
curl https://api.letta.com/v1/templates/project_slug/name/versions \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.listtemplateversions(
    project_slug="project_slug",
    name="name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.listtemplateversions("project_slug", "name");

```

```shell
curl -G https://api.letta.com/v1/templates/:project_slug/:name/versions \
     -H "Authorization: Bearer <token>" \
     -d offset=string \
     -d limit=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.listtemplateversions(
    project_slug="project_slug",
    name="name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.listtemplateversions("project_slug", "name");

```