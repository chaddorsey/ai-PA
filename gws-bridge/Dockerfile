FROM node:20-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install gws CLI globally
RUN npm install -g @googleworkspace/cli

WORKDIR /app
COPY package.json ./
RUN npm install --production
COPY server.js ./

EXPOSE 8098
CMD ["node", "server.js"]
