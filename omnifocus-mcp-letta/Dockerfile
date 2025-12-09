# Use Node.js 20 Alpine for smaller image size
FROM node:20-alpine

# Set working directory
WORKDIR /app

# Copy package files first for better Docker layer caching
COPY package*.json ./

# Install all dependencies (including dev dependencies for build)
RUN npm install

# Copy source code
COPY . .

# Build the TypeScript code
RUN npm run build

# Remove dev dependencies to reduce image size
RUN npm prune --production

# Expose the HTTP bridge port
EXPOSE 8888

# Set environment variables for production
ENV NODE_ENV=production
ENV PORT=8888

# Start the simplified MCP server (has built-in HTTP server)
CMD ["npm", "run", "start:simplified"]
