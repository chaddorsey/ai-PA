# Modify Archive

PATCH https://api.letta.com/v1/archives/{archive_id}
Content-Type: application/json

Update an existing archive's name and/or description.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/archives/archive_id \
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
client.archives.modify_archive(
    archive_id="archive_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.archives.modifyArchive("archive_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/archives/:archive_id \
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
client.archives.modify_archive(
    archive_id="archive_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.archives.modifyArchive("archive_id");

```