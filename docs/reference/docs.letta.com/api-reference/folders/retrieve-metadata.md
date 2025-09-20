# Retrieve Metadata

GET https://api.letta.com/v1/folders/metadata

Get aggregated metadata for all folders in an organization.

Returns structured metadata including:
- Total number of folders
- Total number of files across all folders
- Total size of all files
- Per-source breakdown with file details (file_name, file_size per file) if include_detailed_per_source_metadata is True

## Examples

```shell
curl https://api.letta.com/v1/folders/metadata \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.retrieve_metadata()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.retrieveMetadata();

```

```shell
curl -G https://api.letta.com/v1/folders/metadata \
     -H "Authorization: Bearer <token>" \
     -d include_detailed_per_source_metadata=true
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.retrieve_metadata()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.retrieveMetadata();

```