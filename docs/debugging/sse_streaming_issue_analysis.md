# SSE Streaming Issue Analysis

## Symptom
User sees "✓ Completed: search_slack_messages, search_slack_messages, search_slack_messages" instead of the actual agent response.

## Evidence
1. Letta logs show `assistant_message` with `has_content=true` at 22:51:40
2. Server completed thread with full `response_content` in `/complete` call
3. Frontend only showed the fallback completion message

## Root Cause Candidates

### 1. SSE Event Never Yielded (UNLIKELY)
The code at line 845-853 should yield the text:
```python
elif msg_type == "assistant_message":
    content = event_data.get("content", "")
    if content:
        assistant_response_parts.append(content)
        cleaned_content = clean_response_for_user(content)
        if cleaned_content:
            yield f"data: {json.dumps({'type': 'text', 'content': cleaned_content})}\n\n"
```

Since `assistant_response_parts` was populated (evidenced by `/complete` having the full response), the code DID execute and store the content. The yield should have happened.

### 2. SSE Buffering Issue (POSSIBLE)
Flask's Response generator may buffer output. The code uses:
```python
return Response(
    generate(),
    mimetype="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
)
```

**Missing**: The `X-Accel-Buffering: no` header for nginx/proxy environments.

### 3. Frontend Connection Lost (POSSIBLE)
The 48-second gap between `assistant_message` (22:51:40) and `user_message` (22:52:28) is suspicious. During this time:
- Multiple keepalive pings were sent
- The frontend connection may have closed due to timeout
- The text event may have been sent but not received

### 4. Letta Memory Compaction Interrupt (LIKELY)
Looking at the stream sequence:
1. `assistant_message` - agent response
2. 48-second gap with keepalive pings
3. `user_message` - Letta's internal memory compaction alert
4. `stop_reason`

The `user_message` being injected by Letta's memory system mid-stream could cause issues:
- The code doesn't handle `user_message` event type in streaming
- This could cause the loop to exit early or skip processing

### 5. Queue Race Condition (POSSIBLE)
The code uses a queue between background thread and main thread:
```python
event_queue.get(timeout=KEEPALIVE_PING_INTERVAL)
```

If the background thread finishes and puts "done" in the queue before the main thread processes the "assistant_message", the text could be lost.

## Recommendations

### Immediate Fixes

1. **Add X-Accel-Buffering header**:
```python
headers={
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # For nginx proxies
}
```

2. **Handle user_message event type** (even if just to log and skip):
```python
elif msg_type == "user_message":
    # Letta memory compaction alert - ignore for streaming
    logger.debug("letta_memory_compaction", agent_id=selected_agent_id)
```

3. **Add explicit flush after text yield**:
Unfortunately Flask generators don't have explicit flush, but we can ensure immediate delivery by avoiding buffering.

### Diagnostic Improvements

1. **Log the actual yield**:
```python
if cleaned_content:
    logger.info("yielding_text_event", length=len(cleaned_content))
    yield f"data: {json.dumps({'type': 'text', 'content': cleaned_content})}\n\n"
```

2. **Frontend debugging**: Add console.log in the SSE handler to see what events are actually received.

### Longer-term Fixes

1. **Consider using Flask-SSE or a proper SSE library** that handles buffering correctly.

2. **Add response confirmation**: Have the frontend acknowledge receipt of text events.

3. **Fallback mechanism**: If no text event received after tools complete but stream ends, fetch the response from `/complete` endpoint.

## Testing Approach

1. Add logging around the yield statement
2. Use browser DevTools Network tab to watch the SSE stream in real-time
3. Compare timestamps between server yield and frontend receipt
4. Test with different message lengths and agent response times

## Files to Modify

- `pa-web-ui/app.py`: Lines 845-853 (add logging), Response headers
- `pa-web-ui/static/js/chat.js`: Add SSE debug logging
