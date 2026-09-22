# 文旅创新智脑 · 前端生产镜像
# 工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署
#
# 多阶段构建：Node 构建静态产物 → Nginx 托管，运行镜像不含 Node 与源码。
FROM node:20-alpine AS build

WORKDIR /app

# 先装依赖再拷源码：源码变更不会让依赖层缓存失效，构建更快
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY . .
# 构建期做一次类型检查，避免把类型错误带进产物
RUN npm run typecheck && npm run build

FROM nginx:1.27-alpine AS runtime

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
