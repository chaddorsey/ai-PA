# Get Sources Metadata

GET https://api.letta.com/v1/sources/metadata

Get aggregated metadata for all sources in an organization.

Returns structured metadata including:
- Total number of sources
- Total number of files across all sources
- Total size of all files
- Per-source breakdown with file details (file_name, file_size per file) if include_detailed_per_source_metadata is True

## Examples

```shell
curl https://api.letta.com/v1/sources/metadata \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.sources.get_sources_metadata()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.getSourcesMetadata();

```

```shell
curl -G https://api.letta.com/v1/sources/metadata \
     -H "Authorization: Bearer <token>" \
     -d include_detailed_per_source_metadata=true
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.sources.get_sources_metadata()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.sources.getSourcesMetadata();

```