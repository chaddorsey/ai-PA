# Trixie (Debian 13) ships glibc 2.40. The bookworm-based node:20-slim
# only has glibc 2.36, and @googleworkspace/cli's post-2026-04 builds
# fail at runtime with "version `GLIBC_2.39' not found".
FROM node:22-trixie-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install gws CLI globally
RUN npm install -g @googleworkspace/cli

WORKDIR /app
COPY package.json ./
RUN npm install --production
COPY server.js ./

EXPOSE 8098
CMD ["node", "server.js"]
