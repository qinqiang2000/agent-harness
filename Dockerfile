FROM python:3.11-slim

# 使用国内镜像源加速
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null

# 安装 SSH 客户端和基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/agent-harness

# 先装依赖（利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 复制项目代码
COPY . .

# SSH 密钥目录（运行时通过 volume 挂载）
RUN mkdir -p agent_cwd/ssh-keys/aws agent_cwd/ssh-keys/tencent

EXPOSE 9123

# 容器内固定 9123，宿主机端口通过 docker-compose.yml 的 PORT 环境变量映射
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9123"]
