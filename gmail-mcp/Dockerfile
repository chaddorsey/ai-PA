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
RUN mkdir -p /gmail-server /root/.gmail-mcp
ENV NODE_ENV=production
ENV GMAIL_CREDENTIALS_PATH=/gmail-server/credentials.json
ENV GMAIL_OAUTH_PATH=/root/.gmail-mcp/gcp-oauth.keys.json

EXPOSE 7331
CMD ["node", "dist/server-http.js"]
