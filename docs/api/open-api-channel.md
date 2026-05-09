# Open API Channel 接口文档

> 版本：1.0.0  
> Base URL：`http://<host>:<port>`  
> 所有接口（除鉴权接口）需在 Header 中携带 `token`

---

## 通用响应格式

```json
{
  "errcode": "0000",
  "description": "操作成功",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| errcode | string | 错误码，`000000` 表示成功 |
| description | string | 描述信息 |
| data | object/array/null | 业务数据 |

### 错误码说明

| errcode | 说明 |
|---------|------|
| `0000` | 成功 |
| `100001` | 签名验证失败 |
| `100002` | 任务不存在或已过期 |
| `100003` | token 无效或已过期 |
| `500000` | 服务内部错误 |
| `500001` | 异步任务处理失败 |
| `500002` | 图片识别失败（URL 不可达、图片过大、MIME 不支持、vision 服务异常等） |

---

## 1. 获取 Token

### 接口说明

获取 API 访问凭证。Token 有效期 24 小时，过期后需重新获取。

### 请求

```
GET /open-api/get_token
```

### 请求参数

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| appid | query | string | 是 | 接口凭证 ID |
| create_time | query | string | 是 | 时间戳（秒），如 `1569397773` |
| sign | query | string | 是 | 签名：`md5(appid + create_time + app_key)` |

### 签名生成示例

```python
import hashlib, time

appid = "your_app_id"
app_key = "your_app_key"
create_time = str(int(time.time()))
sign = hashlib.md5((appid + create_time + app_key).encode()).hexdigest()
```

### 请求示例

```bash
curl "http://host/open-api/get_token?appid=your_app_id&create_time=1569397773&sign=258eec31..."
```

### 响应示例

```json
{
  "errcode": "0000",
  "description": "操作成功",
  "data": {
    "token": "4ac37cb2e9c740dba4b75a34d5358802",
    "expires_in": "86400"
  }
}
```

### 响应 data 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| token | string | 访问凭证，后续接口 Header 中携带 |
| expires_in | string | 有效期（秒） |

---

## 2. 初始化会话

### 接口说明

创建一个新的会话，返回 `ai_agent_cid` 作为后续问答的会话标识。

### 请求

```
GET /open-api/ask/ask_init
```

### 请求 Header

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| token | string | 是 | 通过鉴权接口获取的 token |

### 请求示例

```bash
curl -H "token: 4ac37cb2e9c740dba4b75a34d5358802" \
  "http://host/open-api/ask/ask_init"
```

### 响应示例

```json
{
  "errcode": "0000",
  "description": "操作成功",
  "data": {
    "ai_agent_cid": "17ad7f4ab65b4aedadb3b72caf6a86cd",
    "biz_type": "AI_AGENT"
  }
}
```

### 响应 data 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| ai_agent_cid | string | 会话 ID，后续问答接口必传 |
| biz_type | string | 业务类型，固定值 `AI_AGENT` |

---

## 3. 同步问答（非流式）

### 接口说明

发送问题并同步等待 AI 回答，适合对响应时延要求不高的场景。

### 请求

```
POST /open-api/ask/answer_no_stream
```

### 请求 Header

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| token | string | 是 | 访问凭证 |
| Content-Type | string | 是 | `application/json` |

### 请求 Body

```json
{
  "question": "你好",
  "ai_agent_cid": "17ad7f4ab65b4aedadb3b72caf6a86cd",
  "uid": "user_001",
  "user_name": "张三",
  "show_question": "你好",
  "msg_type": "TEXT",
  "params": {},
  "images": [
    "https://your-cdn.com/screenshots/error-1.png"
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| question | string | 是 | 用户问题 |
| ai_agent_cid | string | 是 | 会话 ID，由初始化接口获取 |
| skill | string | 否 | 指定使用的 skill 名称，不传则使用默认 skill |
| uid | string | 否 | 用户 ID |
| user_name | string | 否 | 用户姓名 |
| show_question | string | 否 | 展示用问题文本 |
| msg_type | string | 否 | 消息类型，默认 `TEXT` |
| params | object | 否 | 自定义扩展参数 |
| images | string[] | 否 | 图片 URL 列表（`http://` / `https://`），最多 5 张，每轮均可传；详见[图片问答说明](#图片问答说明) |

### 请求示例

```bash
curl -X POST \
  -H "token: 4ac37cb2e9c740dba4b75a34d5358802" \
  -H "Content-Type: application/json" \
  -d '{"question":"你好","ai_agent_cid":"17ad7f4ab65b4aedadb3b72caf6a86cd"}' \
  "http://host/open-api/ask/answer_no_stream"
```

#### 带图片的同步问答

```bash
curl -X POST \
  -H "token: 4ac37cb2e9c740dba4b75a34d5358802" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "这个报错怎么解决？",
    "ai_agent_cid": "17ad7f4ab65b4aedadb3b72caf6a86cd",
    "images": [
      "https://your-cdn.com/screenshots/error-1.png",
      "https://your-cdn.com/screenshots/error-2.png"
    ]
  }' \
  "http://host/open-api/ask/answer_no_stream"
```

### 响应示例

```json
{
  "errcode": "0000",
  "description": "操作成功",
  "data": [
    {
      "answer": "你好！我是发票云智能客服，请问有什么可以帮您？",
      "robot_answer_type": "QA_DIRECT",
      "robot_answer_message_type": "MESSAGE",
      "ai_agent_cid": "17ad7f4ab65b4aedadb3b72caf6a86cd",
      "roundid": null,
      "transfer_result": "NO_ACTION"
    }
  ]
}
```

### 响应 data 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| answer | string | AI 回答内容 |
| robot_answer_type | string | 回答类型，固定 `QA_DIRECT` |
| robot_answer_message_type | string | 消息类型，固定 `MESSAGE` |
| ai_agent_cid | string | 会话 ID |
| roundid | string/null | 消息轮次 ID |
| transfer_result | string | 转人工结果：`NO_ACTION` / `TRANSFER` |

---

## 4. 异步问答（非流式）

### 接口说明

发送问题后立即返回 `task_id`，AI 在后台处理。支持两种方式获取结果：
- **回调**：传入 `callback_url`，结果就绪后主动 POST 到该地址
- **轮询**：通过 [查询异步任务结果](#5-查询异步任务结果) 接口轮询

### 请求

```
POST /open-api/ask/answer_async
```

### 请求 Header

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| token | string | 是 | 访问凭证 |
| Content-Type | string | 是 | `application/json` |

### 请求 Body

```json
{
  "question": "发票云有哪些版本",
  "ai_agent_cid": "17ad7f4ab65b4aedadb3b72caf6a86cd",
  "callback_url": "https://your-server.com/callback",
  "uid": "user_001",
  "user_name": "张三",
  "msg_type": "TEXT",
  "params": {},
  "images": [
    "https://your-cdn.com/screenshots/error-1.png"
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| question | string | 是 | 用户问题 |
| ai_agent_cid | string | 是 | 会话 ID |
| skill | string | 否 | 指定使用的 skill 名称，不传则使用默认 skill |
| callback_url | string | 否 | 结果回调地址，结果就绪后 POST 到此地址 |
| uid | string | 否 | 用户 ID |
| user_name | string | 否 | 用户姓名 |
| show_question | string | 否 | 展示用问题文本 |
| msg_type | string | 否 | 消息类型，默认 `TEXT` |
| params | object | 否 | 自定义扩展参数 |
| images | string[] | 否 | 图片 URL 列表（`http://` / `https://`），最多 5 张，每轮均可传；详见[图片问答说明](#图片问答说明) |

### 请求示例

```bash
curl -X POST \
  -H "token: 4ac37cb2e9c740dba4b75a34d5358802" \
  -H "Content-Type: application/json" \
  -d '{"question":"发票云有哪些版本","ai_agent_cid":"17ad7f4ab65b4aedadb3b72caf6a86cd","callback_url":"https://your-server.com/callback"}' \
  "http://host/open-api/ask/answer_async"
```

### 响应示例

```json
{
  "errcode": "0000",
  "description": "操作成功",
  "data": {
    "task_id": "766d7536e1eb4a9db74936df519f95c1",
    "ai_agent_cid": "17ad7f4ab65b4aedadb3b72caf6a86cd",
    "status": "PENDING"
  }
}
```

### 响应 data 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | string | 异步任务 ID，用于轮询结果 |
| ai_agent_cid | string | 会话 ID |
| status | string | 任务状态，初始为 `PENDING` |

### 回调 Payload（POST 到 callback_url）

结果就绪后，服务端会向 `callback_url` 发起 POST 请求，Body 格式如下：

```json
{
  "errcode": "0000",
  "description": "操作成功",
  "data": {
    "task_id": "766d7536e1eb4a9db74936df519f95c1",
    "status": "DONE",
    "ai_agent_cid": "17ad7f4ab65b4aedadb3b72caf6a86cd",
    "answer": "发票云共有以下版本：标准版、星瀚旗舰版、星空旗舰版、国际版",
    "robot_answer_type": "QA_DIRECT",
    "transfer_result": "NO_ACTION"
  }
}
```

> 注意：每个 `ai_agent_cid` 同一时间只能有一个请求在处理（会话独占）。如需并发问答，请为每次异步任务使用独立的 `ai_agent_cid`。

---

## 5. 查询异步任务结果

### 接口说明

轮询异步任务的处理结果。建议在未收到回调或回调超时时使用。

### 请求

```
GET /open-api/ask/answer_async/{task_id}
```

### 请求 Header

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| token | string | 是 | 访问凭证 |

### 路径参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | string | 是 | 异步任务 ID |

### 请求示例

```bash
curl -H "token: 4ac37cb2e9c740dba4b75a34d5358802" \
  "http://host/open-api/ask/answer_async/766d7536e1eb4a9db74936df519f95c1"
```

### 响应示例（处理中）

```json
{
  "errcode": "0000",
  "description": "操作成功",
  "data": {
    "task_id": "766d7536e1eb4a9db74936df519f95c1",
    "status": "PENDING",
    "ai_agent_cid": "17ad7f4ab65b4aedadb3b72caf6a86cd",
    "answer": null,
    "robot_answer_type": "QA_DIRECT",
    "transfer_result": null
  }
}
```

### 响应示例（处理完成）

```json
{
  "errcode": "0000",
  "description": "操作成功",
  "data": {
    "task_id": "766d7536e1eb4a9db74936df519f95c1",
    "status": "DONE",
    "ai_agent_cid": "17ad7f4ab65b4aedadb3b72caf6a86cd",
    "answer": "发票云共有以下版本：标准版、星瀚旗舰版、星空旗舰版、国际版",
    "robot_answer_type": "QA_DIRECT",
    "transfer_result": "NO_ACTION"
  }
}
```

### 响应示例（任务异常）

```json
{
  "errcode": "500001",
  "description": "处理失败，请重试",
  "data": null
}
```

### 响应 data 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | string | 任务 ID |
| status | string | `PENDING`：处理中 / `DONE`：完成 / `ERROR`：异常 |
| ai_agent_cid | string | 会话 ID |
| answer | string/null | AI 回答，`PENDING` 时为 null |
| robot_answer_type | string | 回答类型 |
| transfer_result | string/null | 转人工结果 |

> 任务结果默认保留 3600 秒（1 小时），超时后返回 `errcode=100002`。

---

## 6. 结束会话

### 接口说明

销毁指定会话，释放服务端会话资源。会话结束后，使用相同 `ai_agent_cid` 发起问答将开启新会话。

### 请求

```
POST /open-api/ask/end_session
```

### 请求 Header

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| token | string | 是 | 访问凭证 |
| Content-Type | string | 是 | `application/json` |

### 请求 Body

```json
{
  "ai_agent_cid": "17ad7f4ab65b4aedadb3b72caf6a86cd"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| ai_agent_cid | string | 是 | 要销毁的会话 ID |

### 请求示例

```bash
curl -X POST \
  -H "token: 4ac37cb2e9c740dba4b75a34d5358802" \
  -H "Content-Type: application/json" \
  -d '{"ai_agent_cid":"17ad7f4ab65b4aedadb3b72caf6a86cd"}' \
  "http://host/open-api/ask/end_session"
```

### 响应示例

```json
{
  "errcode": "0000",
  "description": "会话已结束",
  "data": null
}
```

---

## 图片问答说明

同步问答、异步问答接口均支持在请求 Body 里传入 `images` 字段，让 AI 结合图片内容作答。典型场景：用户上传报错截图、界面截图、发票图片等。

### 请求格式

```json
{
  "question": "这个报错怎么解决？",
  "ai_agent_cid": "...",
  "images": [
    "https://your-cdn.com/screenshots/error-1.png",
    "https://your-cdn.com/screenshots/error-2.jpg"
  ]
}
```

### 字段约束

| 约束项 | 说明 |
|--------|------|
| 协议 | 仅支持 `http://` / `https://`，不接受 data URI、文件路径或 base64 |
| 数量 | 单次请求最多 5 张，超出直接拒绝 |
| 大小 | 单张不超过 5MB，超出当张作废 |
| 格式 | `image/png` / `image/jpeg` / `image/gif` / `image/webp`；未知 MIME 默认按 PNG 处理，明确不支持的类型（如 SVG）作废 |
| 可访问性 | URL 必须从服务端可访问（公网或 Agent 所在内网可达）；签名 URL 需保证在请求处理期间未过期 |

### 处理流程

1. 服务端并发下载所有图片，校验大小 / MIME 后转 base64
2. 根据当前模型配置的多模态能力，走下列三条路径之一：
   - **原生多模态**（如 `claude`）：base64 图片随消息一同送达模型
   - **降级到 vision_helper**（如 `deepseek` 配置 helper 为 `litellm`）：先由 helper 识别出文字描述，再把描述拼进 prompt 交给主模型
   - **明确不支持且未配 helper**：直接返回错误
3. 每张图的描述会结合当前 `question` 做针对性识别（报错信息、traceId、接口名、界面状态等），避免输出与问题无关的噪声

### 续会话带图

在续会话中（即使用同一个 `ai_agent_cid` 发起的后续请求）也可以继续传入 `images`，本轮图片会以本轮消息附件形式送达，不会污染前几轮的上下文。

### 常见错误

| 现象 | 原因 | 解决 |
|------|------|------|
| 立即返回 "当前模型 xxx 不支持图片识别" | 当前模型无多模态能力且未配 vision_helper | 联系运维切换多模态模型，或配置 vision_helper |
| 返回 "图片识别失败: ..." | vision_helper 调用失败（网关错误、鉴权失败、超时） | 检查 vision_helper 配置及网络连通性 |
| 返回 "图片超过 5MB 上限" | 单张图片过大 | 客户端压缩后再传 |
| 返回 "images 最多 5 张" | 超过数量限制 | 合并或拆分为多次请求 |
| 返回 "图片 URL 必须以 http:// 或 https:// 开头" | URL 协议不合法 | 使用公网或服务端可达的 HTTP/HTTPS URL |

---

## 典型调用流程

```
1. GET  /open-api/get_token                      → 获取 token（有效期 24h）
2. GET  /open-api/ask/ask_init                   → 获取 ai_agent_cid
3. POST /open-api/ask/answer_no_stream           → 同步问答（等待结果）
   或
   POST /open-api/ask/answer_async               → 异步问答（立即返回 task_id）
   GET  /open-api/ask/answer_async/{task_id}     → 轮询结果（或等待回调）
4. POST /open-api/ask/end_session                → 结束会话
```
