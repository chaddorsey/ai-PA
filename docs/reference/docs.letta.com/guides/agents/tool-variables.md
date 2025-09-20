# Using Tool Variables

You can use **tool variables** to specify environment variables available to your custom tools.
For example, if you set a tool variable `PASSWORD` to `banana`, then write a custom function that prints `os.getenv('PASSWORD')` in the tool, the function will print `banana`.

## Assigning tool variables in the ADE

To assign tool variables in the Agent Development Environment (ADE), click on **Env Vars** to open the **Environment Variables** viewer:

<img src="file:cddf0e2d-569f-4682-9d0f-676bbfdc40b5" />

Once in the **Environment Variables** viewer, click **+** to add a new tool variable if one does not exist.

<img src="file:ba6432cb-52d5-448f-a907-f5189020b42f" />

## Assigning tool variables in the API / SDK

You can also assign tool variables on agent creation in the API with the `tool_exec_environment_variables` parameter:

<CodeGroup>
  ```curl title="curl" {7-9}
  curl -X POST http://localhost:8283/v1/agents/ \
       -H "Content-Type: application/json" \
       -d '{
    "memory_blocks": [],
    "llm":"openai/gpt-4o-mini",
    "embedding":"openai/text-embedding-3-small",
    "tool_exec_environment_variables": {
        "COMPOSIO_ENTITY": "banana"
    }
  }'
  ```

  ```python title="python" {5-7}
  agent_state = client.agents.create(
      memory_blocks=[],
      model="openai/gpt-4o-mini",
      embedding="openai/text-embedding-3-small",
      tool_exec_environment_variables={
          "COMPOSIO_ENTITY": "banana"
      }
  )
  ```

  ```typescript title="node.js" {5-7}
  const agentState = await client.agents.create({
      memoryBlocks: [],
      model: "openai/gpt-4o-mini",
      embedding: "openai/text-embedding-3-small",
      toolExecEnvironmentVariables: {
          "COMPOSIO_ENTITY": "banana"
      }
  });
  ```
</CodeGroup>
