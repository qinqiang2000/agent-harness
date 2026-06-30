# Jenkins 自动化测试触发与状态追踪接口文档

## 概述

通过 Jenkins Remote API 触发自动化测试任务，并追踪构建状态直至完成。整个流程分三步：**触发构建 → 获取构建号 → 轮询状态**。

> 注意：自动化测试任务（`at-automated-test`）耗时较长，预计 30 分钟以上，轮询时需设置足够长的超时时间。

---

## 第一步：触发构建

### 请求

```
POST http://jump-test.piaozone.com:8080/job/at-automated-test/buildWithParameters
```

### 认证

使用 HTTP Basic Auth：
- 用户名：`chuang_li`
- 密码/Token：`110a928885da4fe07b6b06b95a33a37d9b`

### 请求参数（Query String）

| 参数名         | 类型    | 必填 | 说明                            | 示例值   |
|--------------|---------|------|---------------------------------|---------|
| token        | string  | 是   | Jenkins 构建触发 token           | `JAaZnYeyAeHXN5eN` |
| RUN_MODE     | string  | 是   | 运行模式，`full`=全量，`smoke`=冒烟 | `full`  |
| THREADS      | string  | 是   | 并发线程数                        | `4`     |
| ISSUE_MODE   | string  | 否   | 缺陷模式，默认 `smoke`             | `smoke` |
| ISSUE_TYPE   | string  | 否   | 缺陷类型，默认 `blue`              | `blue`  |
| SCENARIO_FILE| string  | 否   | 指定场景文件，不填则跑全部           | ``      |
| ISSUE_ID     | string  | 否   | 指定缺陷 ID                       | ``      |

### 示例（curl）

```bash
curl -v -X POST \
  -u chuang_li:110a928885da4fe07b6b06b95a33a37d9b \
  "http://jump-test.piaozone.com:8080/job/at-automated-test/buildWithParameters?token=JAaZnYeyAeHXN5eN&RUN_MODE=full&THREADS=4"
```

### 响应

- **状态码：** `201 Created` 表示成功加入队列
- **关键响应头：** `Location` 字段包含队列 URL，从中提取**队列 ID**

```
HTTP/1.1 201 Created
Location: http://jump-test.piaozone.com:8080/queue/item/29416/
```

从 Location URL 中提取队列 ID，示例中为 `29416`。

---

## 第二步：获取构建号

队列任务分配到 Executor 后会生成实际构建号，通过队列 ID 查询。

### 请求

```
GET http://jump-test.piaozone.com:8080/queue/item/{queueId}/api/json
```

### 示例（curl）

```bash
curl -s \
  -u chuang_li:110a928885da4fe07b6b06b95a33a37d9b \
  "http://jump-test.piaozone.com:8080/queue/item/29416/api/json"
```

### 响应示例（等待中，尚未分配）

```json
{
  "id": 29416,
  "_class": "hudson.model.Queue$WaitingItem",
  "why": "Finished waiting",
  "executable": null
}
```

### 响应示例（已分配构建号）

```json
{
  "id": 29416,
  "executable": {
    "_class": "org.jenkinsci.plugins.workflow.job.WorkflowRun",
    "number": 123,
    "url": "http://jump-test.piaozone.com:8080/job/at-automated-test/123/"
  }
}
```

从 `executable.number` 字段获取**构建号**（示例中为 `123`）。

> **注意：** `executable` 为 `null` 时说明还在排队，需间隔 3~5 秒重试。

---

## 第三步：轮询构建状态

使用构建号轮询，直到 `building` 为 `false` 时读取最终结果。

### 请求

```
GET http://jump-test.piaozone.com:8080/job/at-automated-test/{buildNumber}/api/json
```

### 示例（curl）

```bash
curl -s \
  -u chuang_li:110a928885da4fe07b6b06b95a33a37d9b \
  "http://jump-test.piaozone.com:8080/job/at-automated-test/123/api/json"
```

### 关键响应字段

| 字段       | 类型    | 说明                                      |
|----------|---------|-------------------------------------------|
| number   | int     | 构建号                                    |
| building | boolean | `true` 表示构建中，`false` 表示已结束      |
| result   | string  | 构建结果，`building=true` 时为 `null`      |

### result 枚举值

| 值          | 含义     |
|-----------|--------|
| `SUCCESS` | 构建成功   |
| `FAILURE` | 构建失败   |
| `ABORTED` | 已中止    |
| `null`    | 还在执行中  |

### 响应示例（进行中）

```json
{
  "number": 123,
  "building": true,
  "result": null
}
```

### 响应示例（已完成）

```json
{
  "number": 123,
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
    f"{BASE_URL}/job/at-automated-test/buildWithParameters",
    auth=AUTH,
    params={
        "token": "JAaZnYeyAeHXN5eN",
        "RUN_MODE": "full",
        "THREADS": "4"
    }
)
assert resp.status_code == 201, f"触发失败: {resp.status_code}"

# 从 Location 头提取队列 ID
location = resp.headers["Location"]
queue_id = re.search(r"/queue/item/(\d+)/", location).group(1)

# 第二步：等待分配构建号
build_number = None
while build_number is None:
    time.sleep(5)
    queue_resp = requests.get(f"{BASE_URL}/queue/item/{queue_id}/api/json", auth=AUTH)
    executable = queue_resp.json().get("executable")
    if executable:
        build_number = executable["number"]

# 第三步：轮询构建结果（自动化测试耗时较长，建议间隔 30 秒）
while True:
    build_resp = requests.get(f"{BASE_URL}/job/at-automated-test/{build_number}/api/json", auth=AUTH)
    data = build_resp.json()
    if not data["building"]:
        result = data["result"]  # SUCCESS / FAILURE / ABORTED
        break
    time.sleep(30)
```

---

## 查看构建日志

如需获取控制台输出排查问题：

```bash
curl -s \
  -u chuang_li:110a928885da4fe07b6b06b95a33a37d9b \
  "http://jump-test.piaozone.com:8080/job/at-automated-test/{buildNumber}/consoleText"
```

---

## 与 cicd-pipeline 的差异对比

| 项目         | cicd-pipeline              | at-automated-test          |
|------------|---------------------------|---------------------------|
| 用途         | 服务构建 & 部署               | 自动化测试                  |
| 触发 token   | `410xCyjlF88nE63t`         | `JAaZnYeyAeHXN5eN`         |
| 主要参数     | SERVICE、BRANCH、DEPLOY     | RUN_MODE、THREADS          |
| 预计耗时     | ~2 分钟                    | 30 分钟以上                 |
| 轮询间隔建议 | 15 秒                      | 30 秒                      |
