# Get Token from Browser After OAuth

Since `mcp-remote` completed OAuth successfully, you can extract the token from your browser.

## Method 1: Browser DevTools (Recommended)

1. **Open Browser DevTools** (F12 or Cmd+Option+I)
2. Go to **Network** tab
3. **Filter by**: `mcp.atlassian.com`
4. Look for requests to `https://mcp.atlassian.com/v1/mcp` or `/v1/sse`
5. Click on a request
6. Go to **Headers** tab
7. Look for **Request Headers** → `Authorization: Bearer <token>`
8. Copy the token value (everything after "Bearer ")

## Method 2: Check mcp-remote Output

If `mcp-remote` is still running, check its output for token information:

```bash
# If mcp-remote is running, check its output
ps aux | grep mcp-remote
# Look at the terminal where you ran mcp-remote
```

## Method 3: Make Test Request Through mcp-remote

1. Keep `mcp-remote` running:
   ```bash
   mcp-remote https://mcp.atlassian.com/v1/mcp
   ```

2. In another terminal, make a test request (if mcp-remote exposes HTTP):
   ```bash
   # This might not work if mcp-remote uses stdio
   curl http://localhost:3736/mcp
   ```

## Save the Token

Once you have the token:

```bash
echo "YOUR_TOKEN_HERE" > ~/.atlassian-rovo-token.txt
```

Then configure Letta to use it (see next steps).

## Next Steps

After getting the token:
1. Set environment variable: `export ATLASSIAN_ROVO_TOKEN="your-token"`
2. Update Letta configuration to use the token
3. Restart Letta: `docker-compose restart letta`

