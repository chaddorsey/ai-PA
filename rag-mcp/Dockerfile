FROM node:20-slim

WORKDIR /app

# Install deps first for better layer caching
COPY package.json package-lock.json* ./
RUN npm ci

# Then copy sources and build
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# Runtime dirs & env
RUN mkdir -p /app/data /app/config
ENV NODE_ENV=production
ENV MCP_SERVER_NAME=rag-tools
ENV MCP_SERVER_VERSION=1.0.0
ENV MCP_SERVER_DESCRIPTION=RAG tools for retrieval-augmented generation
ENV MCP_SERVER_HOST=0.0.0.0
ENV MCP_SERVER_PORT=8082
ENV MCP_SERVER_PATH=/mcp
ENV MCP_LOG_LEVEL=INFO
ENV MCP_LOG_FORMAT=json
ENV MCP_HEALTH_CHECK_PATH=/health

EXPOSE 8082
CMD ["node", "dist/server-http.js"]

