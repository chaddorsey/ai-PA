# Get File Metadata

GET https://api.letta.com/v1/sources/{source_id}/files/{file_id}

Retrieve metadata for a specific file by its ID.

## Examples

```shell
curl https://api.letta.com/v1/sources/source_id/files/file_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.sources.get_file_metadata(
    source_id="source_id",
    file_id="file_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.getFileMetadata("source_id", "file_id");

```

```shell
curl -G https://api.letta.com/v1/sources/:source_id/files/:file_id \
     -H "Authorization: Bearer <token>" \
     -d include_content=true
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.sources.get_file_metadata(
    source_id="source_id",
    file_id="file_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.getFileMetadata("source_id", "file_id");

```