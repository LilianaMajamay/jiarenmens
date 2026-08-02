# ═══════════════════════════════════════════════
# 东方财富实盘选手爬虫 - Docker 镜像
# ═══════════════════════════════════════════════
# 构建: docker build -t jiarenmens .
# 运行: docker compose up -d
# ═══════════════════════════════════════════════

FROM python:3.11-slim-bookworm AS base

# Playwright 系统依赖 + 中文字体（不装系统 Chromium，用 Playwright 自带的）
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖 + Playwright Chromium
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium && \
    playwright install-deps chromium

# ── 生产镜像 ──
FROM base AS production

# 先装依赖再拷源码（利用 Docker 层缓存）
COPY . .
RUN python -c "import src.config"  # 提前触发目录创建

# 环境变量默认值（可通过 .env 或 docker compose 覆盖）
ENV CRAWL_WORKERS=10 \
    CRAWL_LIMIT=500 \
    CRAWL_DATA_DIR=/app/data \
    CRAWL_LOG_DIR=/app/logs

VOLUME ["/app/data", "/app/logs"]

# 默认入口
CMD ["python", "main.py"]
