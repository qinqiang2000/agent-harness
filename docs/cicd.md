# Jenkins CICD 构建触发与状态追踪接口文档

## 概述

通过 Jenkins Remote API 触发构建任务，并追踪构建状态直至完成。整个流程分三步：**触发构建 → 获取构建号 → 轮询状态**。

---

## 第一步：触发构建

### 请求

```
POST http://jump-test.piaozone.com:8080/job/cicd-pipeline/buildWithParameters
```

### 认证

使用 HTTP Basic Auth：
- 用户名：`chuang_li`
- 密码/Token：`110a928885da4fe07b6b06b95a33a37d9b`

### 请求参数（Query String）

| 参数名    | 类型    | 说明                     | 示例值                  |
|---------|---------|--------------------------|------------------------|
| token   | string  | Jenkins 构建触发 token    | `410xCyjlF88nE63t`     |
| SERVICE | string  | 要构建的服务名             | `yunying-dw-service`   |
| BRANCH  | string  | 构建分支                  | `test`                 |
| DEPLOY  | boolean | 是否执行部署               | `true`                 |

### 示例（curl）

```bash
curl -v -X POST \
  -u chuang_li:110a928885da4fe07b6b06b95a33a37d9b \
  "http://jump-test.piaozone.com:8080/job/cicd-pipeline/buildWithParameters?token=410xCyjlF88nE63t&SERVICE=yunying-dw-service&BRANCH=test&DEPLOY=true"
```

### 响应

- **状态码：** `201 Created` 表示成功加入队列
- **关键响应头：** `Location` 字段包含队列 URL，从中提取**队列 ID**

```
HTTP/1.1 201 Created
Location: http://jump-test.piaozone.com:8080/queue/item/29412/
```

从 Location URL 中提取队列 ID，示例中为 `29412`。

---

## 第二步：获取构建号

队列任务在分配到 Executor 后会生成实际构建号，需通过队列 ID 查询。

### 请求

```
GET http://jump-test.piaozone.com:8080/queue/item/{queueId}/api/json
```

### 示例（curl）

```bash
curl -s \
  -u chuang_li:110a928885da4fe07b6b06b95a33a37d9b \
  "http://jump-test.piaozone.com:8080/queue/item/29412/api/json"
```

### 响应示例

```json
{
  "id": 29412,
  "executable": {
    "_class": "org.jenkinsci.plugins.workflow.job.WorkflowRun",
    "number": 12693,
    "url": "http://jump-test.piaozone.com:8080/job/cicd-pipeline/12693/"
  }
}
```

从 `executable.number` 字段获取**构建号**（示例中为 `12693`）。

> **注意：** 如果任务还在排队等待，`executable` 字段可能为 `null`，需稍等后重试。

---

## 第三步：轮询构建状态

使用构建号轮询，直到 `building` 为 `false` 时读取最终结果。

### 请求

```
GET http://jump-test.piaozone.com:8080/job/cicd-pipeline/{buildNumber}/api/json
```

### 示例（curl）

```bash
curl -s \
  -u chuang_li:110a928885da4fe07b6b06b95a33a37d9b \
  "http://jump-test.piaozone.com:8080/job/cicd-pipeline/12693/api/json"
```

### 关键响应字段

| 字段       | 类型    | 说明                                      |
|----------|---------|-------------------------------------------|
| number   | int     | 构建号                                    |
| building | boolean | `true` 表示构建中，`false` 表示已结束      |
| result   | string  | 构建结果，`building=true` 时为 `null`      |

### result 枚举值

| 值        | 含义   |
|---------|--------|
| `SUCCESS` | 构建成功 |
| `FAILURE` | 构建失败 |
| `ABORTED` | 已中止   |
| `null`    | 还在执行中 |

### 响应示例（进行中）

```json
{
  "number": 12693,
  "building": true,
  "result": null
}
```

### 响应示例（已完成）

```json
{
  "number": 12693,
  "building": false,
  "result": "SUCCESS"
}
```

---

## 完整流程伪代码

```python
import requests
import time
import re

BASE_URL = "http://jump-test.piaozone.com:8080"
AUTH = ("chuang_li", "110a928885da4fe07b6b06b95a33a37d9b")

# 第一步：触发构建
resp = requests.post(
    f"{BASE_URL}/job/cicd-pipeline/buildWithParameters",
    auth=AUTH,
    params={
        "token": "410xCyjlF88nE63t",
        "SERVICE": "yunying-dw-service",
        "BRANCH": "test",
        "DEPLOY": "true"
    }
)
assert resp.status_code == 201, f"触发失败: {resp.status_code}"

# 从 Location 头提取队列 ID
location = resp.headers["Location"]
queue_id = re.search(r"/queue/item/(\d+)/", location).group(1)

# 第二步：等待分配构建号
build_number = None
while build_number is None:
    time.sleep(3)
    queue_resp = requests.get(f"{BASE_URL}/queue/item/{queue_id}/api/json", auth=AUTH)
    executable = queue_resp.json().get("executable")
    if executable:
        build_number = executable["number"]

# 第三步：轮询构建结果
while True:
    build_resp = requests.get(f"{BASE_URL}/job/cicd-pipeline/{build_number}/api/json", auth=AUTH)
    data = build_resp.json()
    if not data["building"]:
        result = data["result"]  # SUCCESS / FAILURE / ABORTED
        break
    time.sleep(15)
```

---

## 查看构建日志

如需获取控制台输出排查问题：

```bash
curl -s \
  -u chuang_li:110a928885da4fe07b6b06b95a33a37d9b \
  "http://jump-test.piaozone.com:8080/job/cicd-pipeline/{buildNumber}/consoleText"
```
