# ── 构建阶段：Vue 3 + Vite 编译 ──
FROM --platform=$BUILDPLATFORM node:22-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# ── 运行阶段：nginx 托管静态资源 + 反代 /api ──
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
