# Dev-mode container for Scout web — mirrors scout-api: bind-mount the
# source so edits are picked up by `next dev` instantly.
FROM node:22-alpine

WORKDIR /app

# Install deps based on the lockfile (or package.json if no lockfile yet).
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

EXPOSE 3000
ENV NEXT_TELEMETRY_DISABLED=1

CMD ["npm", "run", "dev"]
