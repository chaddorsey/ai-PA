# Agent Architectures

> Explore all available agent architectures and compare their capabilities

<CardGroup cols={3}>
  <a href="/guides/agents/architectures/memgpt">
    <div>
      <img src="file:6d789a5f-5f8f-4824-b8d7-2a9d0517c34a" alt="Agent architecture card" />

      <img src="file:e2962781-181e-4ea9-bd4e-5c244dae8a62" alt="Agent architecture card" />

      <div>
        MemGPT agents
      </div>

      <div>
        Agents that can edit their own memory
      </div>
    </div>
  </a>

  <a href="/guides/agents/architectures/sleeptime">
    <div>
      <img src="file:0ea2ea03-ef6a-495f-a990-7e34d1fe0b6e" alt="Agent architecture card" />

      <img src="file:5737bb7b-e732-4b56-87f3-e3f727f3ee03" alt="Agent architecture card" />

      <div>
        Sleep-time agents
      </div>

      <div>
        Memory editing via subconscious agents
      </div>
    </div>
  </a>

  <a href="/guides/agents/architectures/low-latency">
    <div>
      <img src="file:e220d005-1c88-43ed-abf1-dca27638f8c9" alt="Agent architecture card" />

      <img src="file:a338509e-26dc-40c5-a1cb-d0407d49dac4" alt="Agent architecture card" />

      <div>
        Low-latency (voice) agents
      </div>

      <div>
        Agents optimized for low-latency settings
      </div>
    </div>
  </a>

  <a href="/guides/agents/architectures/react">
    <div>
      <img src="file:e3491e26-c9f6-462b-8c6f-e98abdc6ad5c" alt="Agent architecture card" />

      <img src="file:26b10d8c-a6c2-447f-af44-db7962248be6" alt="Agent architecture card" />

      <div>
        ReAct agents
      </div>

      <div>
        Tool-calling agents without memory
      </div>
    </div>
  </a>

  <a href="/guides/agents/architectures/workflows">
    <div>
      <img src="file:c5102180-2b06-4f99-aacf-4b91b4401ca6" alt="Agent architecture card" />

      <img src="file:f8628bec-8422-47d1-b5cb-102a19f66ce5" alt="Agent architecture card" />

      <div>
        Workflows
      </div>

      <div>
        LLMs executing sequential tool calls
      </div>
    </div>
  </a>

  <a href="/guides/agents/architectures/stateful-workflows">
    <div>
      <img src="file:88ca76d1-7727-4000-bd6e-d5a742e0e286" alt="Agent architecture card" />

      <img src="file:8f33c27a-afbb-420d-a6f2-db2d1ee70b4c" alt="Agent architecture card" />

      <div>
        Stateful workflows
      </div>

      <div>
        Workflows that can adapt over time
      </div>
    </div>
  </a>
</CardGroup>

## Comparing the architectures

<Note>
  **Unsure of which architecture to use?**

  Consider starting with our default agent architecture (MemGPT), which is highly autonomous and has long-term self-editing memory.
  You can constrain the behavior to be more deterministic (ie more "workflow-like") by adding [tool rules](/guides/agents/tool-rules) to your agent.
</Note>

| Architecture                                                           | Reasoning Traces | Tool Calling | Tool Rules | Persistent Messages | Long-term Memory | Usecase                                  |
| ---------------------------------------------------------------------- | ---------------- | ------------ | ---------- | ------------------- | ---------------- | ---------------------------------------- |
| [MemGPT agents](/guides/agents/architectures/memgpt)                   | â                | â            | â          | â                   | â                | Long-running (perpetual) stateful agents |
| [Sleep-time agents](/guides/agents/architectures/sleeptime)            | â                | â            | â          | â                   | â                | Async (subconscious) memory processing   |
| [Low-latency (voice) agents](/guides/agents/architectures/low-latency) | â                | â            | â          | â                   | â                | Stateful agents with latency constraints |
| [ReAct agents](/guides/agents/architectures/react)                     | â                | â            | â          | â                   | -                | Simple memory-less tool-calling agents   |
| [Workflows](/guides/agents/architectures/workflows)                    | â                | â            | â          | -                   | -                | Predefined, sequential processes         |
| [Stateful workflows](/guides/agents/architectures/stateful-workflows)  | â                | â            | â          | -                   | â                | Workflows that can adapt over time       |
