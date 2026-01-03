# Tool Overlap Analysis: search_user_watch_history vs query_user_watch_history

## Comparison

### `search_user_watch_history`
- **Parameters**: `username` (required), `query` (required)
- **Endpoint**: `content-database:5126/user/{username}/search?q={query}`
- **Returns**: `results` list, `count`
- **Purpose**: Simple title text search
- **Use case**: "Have I watched Breaking Bad?"

### `query_user_watch_history`
- **Parameters**: `username` (optional, defaults to 'chad'), `service` (optional), `title_search` (optional), `limit` (optional, defaults to 50)
- **Endpoint**: `content-database-api:5126/user/history?username={}&service={}&title={}&limit={}`
- **Returns**: `entries` list, `count`
- **Purpose**: Comprehensive watch history querying
- **Use cases**: 
  - Title search: "Have I watched Breaking Bad?" (using `title_search`)
  - Service filter: "What have I watched on Netflix?" (using `service`)
  - Recent activity: "What have I watched recently?" (no filters, with `limit`)
  - Combined: "Recent Netflix shows with 'Breaking' in title"

## Overlap: YES

**Both tools can search by title:**
- `search_user_watch_history(query="breaking")` 
- `query_user_watch_history(title_search="breaking")`

They perform the **same core function** (title search) but:
1. Hit **different endpoints** (`content-database` vs `content-database-api`) - this may indicate they're different services or a naming inconsistency
2. Have **different return field names** (`results` vs `entries`)

## Recommendation: Keep `query_user_watch_history`

### Why `query_user_watch_history` is superior:
1. **More flexible** - Can filter by service, limit results
2. **More comprehensive** - Can do title search AND other queries (service filtering, recent activity)
3. **Better defaults** - Optional username with default, configurable limit
4. **More powerful** - Can answer broader questions beyond just "have I watched X?"

### Why remove `search_user_watch_history`:
1. **Redundant** - Everything it does can be done with `query_user_watch_history(title_search=...)`
2. **Less flexible** - Only does title search, nothing else
3. **Different endpoint** - May cause confusion if both services exist

### Exception:
If the endpoints are actually different services with different capabilities, we should:
1. Investigate what each endpoint provides
2. Keep both if they serve different purposes
3. Or consolidate to one if they're duplicates

## For Agent Allocation:

**Main Agent**: Should keep `query_user_watch_history` (more flexible for user queries)

**Sleeptime Agent**: Should keep `query_user_watch_history` (better for pattern analysis - can filter by service, get recent activity, etc.)

**Remove from both**: `search_user_watch_history` (unless endpoint investigation reveals unique capabilities)

