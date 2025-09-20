# Import Agent

POST https://api.letta.com/v1/agents/import
Content-Type: multipart/form-data

Import a serialized agent file and recreate the agent(s) in the system.
Returns the IDs of all imported agents.

## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/import \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: multipart/form-data" \
     -F file=@string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.import_file()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";
import * as fs from "fs";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.importFile(fs.createReadStream("/path/to/your/file"), {});

```

```shell
curl -X POST https://api.letta.com/v1/agents/import \
     -H "x-override-embedding-model: string" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: multipart/form-data" \
     -F file=@<filename1>
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.import_file()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";
import * as fs from "fs";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.importFile(fs.createReadStream("/path/to/your/file"), {});

```