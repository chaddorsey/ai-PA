FROM node:20-slim

WORKDIR /app

# Install deps first for better layer caching
COPY package.json package-lock.json* ./
RUN npm ci

# Then copy sources and build
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# Runtime environment
ENV NODE_ENV=production
ENV PORT=8083
ENV HEALTH_CHECK_INTERVAL=30

EXPOSE 8083
CMD ["node", "dist/index.js"]

