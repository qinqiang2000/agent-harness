# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 系统依赖：
#  - curl/ca-certificates: 装 Node 用
#  - libgl1/libglib2.0-0/libgomp1: rapidocr-onnxruntime 运行时依赖
#  - default-jre-headless: saxonche (Saxon-HE) 的 JVM 依赖；不用 XSLT 2.0/3.0 可去掉
#  - build-essential: 兜底，部分包没 wheel 时本地编译
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
        libgl1 libglib2.0-0 libgomp1 \
        default-jre-headless \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 (Claude Agent SDK 通过 spawn @anthropic-ai/claude-code 子进程工作)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

WORKDIR /app

# 先装依赖以利用层缓存
COPY requirements.txt .
RUN pip install -r requirements.txt

# 再拷贝代码
COPY . .

# 关键目录预创建（即使没挂卷也能跑）
RUN mkdir -p /app/agent_cwd /app/log /app/plugins/installed

EXPOSE 9090

# 直接 uvicorn,不走 run.sh; 不要 --reload
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9123"]
