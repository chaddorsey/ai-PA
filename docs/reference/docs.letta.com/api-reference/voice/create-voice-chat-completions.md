# Create Voice Chat Completions

POST https://api.letta.com/v1/voice-beta/{agent_id}/chat/completions
Content-Type: application/json

## Examples

```shell
curl -X POST https://api.letta.com/v1/voice-beta/agent_id/chat/completions \
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
client.voice.create_voice_chat_completions(
    agent_id="agent_id",
    request={"key": "value"},
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.voice.createVoiceChatCompletions("agent_id", {
    "key": "value"
});

```

```shell
curl -X POST https://api.letta.com/v1/voice-beta/:agent_id/chat/completions \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "string": {}
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.voice.create_voice_chat_completions(
    agent_id="agent_id",
    request={"key": "value"},
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.voice.createVoiceChatCompletions("agent_id", {
    "key": "value"
});

```