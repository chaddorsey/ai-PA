# Sleep-time Agents

> Based on the new sleep-time compute research paper

<Note>
  To learn more about sleep-time compute, check out our [blog](https://www.letta.com/blog/sleep-time-compute) and [research paper](https://arxiv.org/abs/2504.13171).
</Note>

<img src="file:19a64aa6-2cc7-4878-a9dc-4e1f4d42c7e5" />

<img src="file:be024d33-80f1-4cac-b58a-3cc0c90c08f0" />

In Letta, you can create special **sleep-time agents** that share the memory of your primary agents, but run in the background and can modify the memory asynchronously. You can think of sleep-time agents as a special form of multi-agent architecture, where all agents in the system share one or more memory blocks. A single agent can have one or more associated sleep-time agents to process data such as the conversation history or data sources to manage the memory blocks of the primary agent.

To enable sleep-time agents for your agent, create the agent with type `sleeptime_agent`. When you create an agent of this type, this will automatically create:

* A primary agent (i.e. general-purpose agent) tools for `send_message`, `conversation_search`, and `archival_memory_search`. This is your "main" agent that you configure and interact with.
* A sleep-time agent with tools to manage the memory blocks of the primary agent. It is possible that additional, ephemeral sleep-time agents will be created when you add data into data sources of the primary agent.

## Background: Memory Blocks

Sleep-time agents specialize in generating *learned context*. Given some original context (e.g. the conversation history, a set of files) the sleep-time agent will reflect on the original context to iteratively derive a learned context. The learned context will reflect the most important pieces of information or insights from the original context.

In Letta, the learned context is saved in a memory block. A memory block represents a labeled section of the context window with an associated character limit. Memory blocks can be shared between multiple agents. A sleep-time agent will write the learned context to a memory block, which can also be shared with other agents that could benefit from those learnings.

Memory blocks can be access directly through the API to be updated, retrieved, or deleted.

<CodeGroup>
  ```python title="python"
  # get a block by label
  block = client.agents.blocks.retrieve(agent_id=agent_id, block_label="persona")

  # get a block by ID
  block = client.blocks.retrieve(block_id=block_id)
  ```

  ```typescript title="node.js"
  // get a block by label
  const block = await client.agents.blocks.retrieve(agentId, "persona");

  // get a block by ID
  const block = await client.blocks.retrieve(blockId);
  ```
</CodeGroup>

When sleep-time is enabled for an agent, there will be one or more sleep-time agents created to manage the memory blocks of the primary agent. These sleep-time agents will run in the background and can modify the memory blocks of the primary agent asynchronously. One sleep-time agent (created when the primary agent is created) will generate learned context from the conversation history to update the memory blocks of the primary agent. Additional ephemeral sleep-time agents will be created when you add data into data sources of the primary agent to process the data sources in the background. These ephemeral agents will create and write to a block specific to the data source, and be deleted once they are finished processing the data sources.

## Sleep-time agent for conversation

<img src="file:780d6c15-35ac-4b31-8e2f-b0ebb379ea6c" />

<img src="file:9704938d-91c7-4d1c-be1e-e31df098d744" />

When a `sleeptime_agent` is created, a primary agent and a sleep-time agent are created as part of a multi-agent group under the hood. The sleep-time agent is responsible for generating learned context from the conversation history to update the memory blocks of the primary agent. The group ensures that for every `N` steps taken by the primary agent, the sleep-time agent is invoked with data containing new messages in the primary agent's message history.

<img src="file:f8260077-8e3b-4570-b3f9-a1fc5c61dcaf" />

### Configuring the frequency of sleep-time updates

The sleep-time agent will be triggered every N-steps (default `5`) to update the memory blocks of the primary agent. You can configure the frequency of updates by setting the `sleeptime_agent_frequency` parameter when creating the agent.

<CodeGroup>
  ```python title="python" maxLines=50
  from letta_client import Letta
  from letta_client.types import SleeptimeManagerUpdate

  client = Letta(token="LETTA_API_KEY")

  # create a sleep-time-enabled agent
  agent = client.agents.create(
      memory_blocks=[
          {"value": "", "label": "human"},
          {"value": "You are a helpful assistant.", "label": "persona"},
      ],
      model="anthropic/claude-3-7-sonnet-20250219",
      embedding="openai/text-embedding-3-small",
      enable_sleeptime=True,
  )
  print(f"Created agent id {agent.id}")

  # get the multi-agent group
  group_id = agent.multi_agent_group.id
  current_frequence = agent.multi_agent_group.sleeptime_agent_frequency
  print(f"Group id: {group_id}, frequency: {current_frequence}")

  # update the frequency to every 2 steps
  group = client.groups.modify(
      group_id=group_id,
      manager_config=SleeptimeManagerUpdate(
          sleeptime_agent_frequency=2
      ),
  )
  ```

  ```typescript title="node.js" maxLines=50
  import { LettaClient, SleeptimeManagerUpdate } from '@letta-ai/letta-client'

  const client = new LettaClient({ token: "LETTA_API_KEY" });

  // create a sleep-time-enabled agent
  const agent = await client.agents.create({
      memoryBlocks: [
          { value: "", label: "human" },
          { value: "You are a helpful assistant.", label: "persona" }
      ],
      model: "anthropic/claude-3-7-sonnet-20250219",
      embedding: "openai/text-embedding-3-small",
      enableSleeptime: true
  });
  console.log(`Created agent id ${agent.id}`);

  // get the multi-agent group
  const groupId = agent.multiAgentGroup.id;
  const currentFrequency = agent.multiAgentGroup.sleeptimeAgentFrequency;
  console.log(`Group id: ${groupId}, frequency: ${currentFrequency}`);

  // update the frequency to every 2 steps
  const group = await client.groups.modify(groupId, {
      managerConfig: {
          sleeptimeAgentFrequency: 2
      } as SleeptimeManagerUpdate
  });
  ```
</CodeGroup>

We recommend keeping the frequency relatively high (e.g. 5 or 10) as triggering the sleep-time agent too often can be expensive (due to high token usage) and has diminishing returns.

## Sleep-time agents for data sources

<img src="file:fc1876af-e534-4fe3-98ee-93d4cf914205" />

<img src="file:be3dc874-0470-4941-8179-937079a9747b" />

Sleep-time-enabled agents will spawn additional ephemeral sleep-time agents when you add data into data sources of the primary agent to process the data sources in the background. These ephemeral agents will create and write to a block specific to the data source, and be deleted once they are finished processing the data sources.

When a file is uploaded to a data source, it is parsed into passages (chunks of text) which are embedded and saved into the main agent's archival memory. If sleeptime is enabled, the sleep-time agent will also process each passage's text to update the memory block corresponding to the data source. The sleep-time agent will create an `instructions` block that contains the data source description, to help guide the learned context generation.

<img src="file:8033965f-56e1-42f5-86c0-4dd86ad78806" />

<Tip>
  Give your data sources an informative `name` and `description` when creating them to help the sleep-time agent generate better learned context, and to help the primary agent understand what the associated memory block is for.
</Tip>

Below is an example of using the SDK to attach a data source to a sleep-time-enabled agent:

<CodeGroup>
  ```python title="python" maxLines=50
  from letta_client import Letta

  client = Letta(token="LETTA_API_KEY")

  agent = client.agents.create(
      memory_blocks=[
          {"value": "", "label": "human"},
          {"value": "You are a helpful assistant.", "label": "persona"},
      ],
      model="anthropic/claude-3-7-sonnet-20250219",
      embedding="openai/text-embedding-3-small",
      enable_sleeptime=True,
  )
  print(f"Created agent id {agent.id}")

  # create a source
  source_name = "employee_handbook"
  source = client.sources.create(
      name=source_name,
      description="Provides reference information for the employee handbook",
      embedding="openai/text-embedding-3-small" # must match agent
  )
  # attach the source to the agent
  client.agents.sources.attach(
      source_id=source.id,
      agent_id=agent.id
  )

  # upload a file: this will trigger processing
  job = client.sources.files.upload(
      file=open("handbook.pdf", "rb"),
      source_id=source.id
  )
  ```

  ```typescript title="node.js" maxLines=50
  import { LettaClient } from '@letta-ai/letta-client'
  import { readFileSync } from 'fs';

  const client = new LettaClient({ token: "LETTA_API_KEY" });

  const agent = await client.agents.create({
      memoryBlocks: [
          { value: "", label: "human" },
          { value: "You are a helpful assistant.", label: "persona" }
      ],
      model: "anthropic/claude-3-7-sonnet-20250219",
      embedding: "openai/text-embedding-3-small",
      enableSleeptime: true
  });
  console.log(`Created agent id ${agent.id}`);

  // create a source
  const sourceName = "employee_handbook";
  const source = await client.sources.create({
      name: sourceName,
      description: "Provides reference information for the employee handbook",
      embedding: "openai/text-embedding-3-small" // must match agent
  });

  // attach the source to the agent
  await client.agents.sources.attach(agent.id, source.id);

  // upload a file: this will trigger processing
  const file = new Blob([readFileSync("handbook.pdf")]);
  const job = await client.sources.files.upload(source.id, file);
  ```
</CodeGroup>

This code will create and attach a memory block with the label `employee_handbook` to the agent. An ephemeral sleep-time agent will be created to process the data source and write to the memory block, and be deleted once all the passages in the data source have been processed.

<Warning>
  Processing each `Passage` from a data source will invoke many LLM requests by the sleep-time agent, so you should only process relatively small files (a few MB) of data.
</Warning>
