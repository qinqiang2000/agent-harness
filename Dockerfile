FROM python:3.11-slim

# 安装 SSH 客户端和基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/agent-harness

# 先装依赖（利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# SSH 密钥目录（运行时通过 volume 挂载）
RUN mkdir -p agent_cwd/ssh-keys/aws agent_cwd/ssh-keys/tencent

EXPOSE 9090

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9090"]
