# Initialize Drive Analytics Memory Blocks

## Quick Setup

To set up the Drive analytics memory structure, ask your agent:

**"Initialize the Drive analytics memory blocks"**

Or call the tool directly:

**"Call initialize_drive_analytics_memory()"**

This will instruct the agent to create the following memory blocks if they don't exist:

1. **`drive_analytics_workspace`** - Initialized with `{}`
2. **`drive_analytics_personal`** - Initialized with `{}`
3. **`drive_analytics_mentions`** - Initialized with `{}`
4. **`drive_analytics_averages`** - Initialized with `{}`
5. **`drive_analytics_config`** - Initialized with:
   ```json
   {
     "my_email": "cdorsey@concord.org",
     "max_days": 50
   }
   ```

## Manual Setup

If you prefer to create them manually, use the memory tool:

```python
# Create each block
memory_create("drive_analytics_workspace", "{}")
memory_create("drive_analytics_personal", "{}")
memory_create("drive_analytics_mentions", "{}")
memory_create("drive_analytics_averages", "{}")
memory_create("drive_analytics_config", '{"my_email": "cdorsey@concord.org", "max_days": 50}')
```

## After Initialization

Once the blocks are created, the scheduled reminders and query tools will work correctly. The blocks will be populated with date-indexed data as the collection tools run.

