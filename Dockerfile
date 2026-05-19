# 应用镜像：基于基础镜像，只复制代码
# 日常迭代只需执行：
#   docker compose build
#   docker compose up -d

FROM agent-harness-base:latest

WORKDIR /opt/agent-harness

# 只复制代码（基础镜像已包含所有依赖）
COPY . .

EXPOSE 9123

# 容器内固定 9123，宿主机端口通过 docker-compose.yml 的 PORT 环境变量映射
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9123"]
