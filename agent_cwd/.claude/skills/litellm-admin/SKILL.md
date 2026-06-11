---
name: litellm-admin
description: >-
  LiteLLM 代理服务的密钥管理。支持查询用户/Key 信息、查看消费额度、为用户增加预算（max_budget）、
  延长有效期、列出所有 key 等管理操作。仅授权管理员使用。
  适用场景：同事请求加额度、查询某人当前余额、列出过期 key、统计本月消费。
  触发词：加额度、加预算、查额度、litellm、key 管理、预算、budget。
---

# LiteLLM 密钥管理

**⚠️ 这是管理员专用 skill，调用前必须验证操作人身份。**

**⚠️ 全程使用 LiteLLM admin API，环境变量 `$LITELLM_BASE_URL` 和 `$LITELLM_MASTER_KEY` 必须可用。**

---

## 安全约束

**授权管理员**（在 prompt 中识别 `operator_name` 字段，必须严格校验）：

授权管理员列表从环境变量 `$LITELLM_ADMINS` 读取（逗号分隔的姓名列表）：

```bash
# 在 Step 1 解析需求前先获取管理员列表
ADMINS=$(echo "$LITELLM_ADMINS" | tr ',' '\n')
```

**校验逻辑**：
- 提取 prompt 中的 `operator_name`
- 检查是否在 `$LITELLM_ADMINS` 列表中（精确匹配）
- 不在列表的请求加额度操作必须拒绝，回复：
  > ⛔ 抱歉，您没有权限执行此操作。请联系管理员（{LITELLM_ADMINS}）。

**额度上限**（从环境变量读取）：
- 单次最多增加 `$LITELLM_MAX_BUDGET_PER_REQUEST`（默认 $50）
- 单 Key 总预算不得超过 `$LITELLM_MAX_TOTAL_BUDGET`（默认 $500）
- 超过上限必须人工二次确认，使用 AskUserQuestion 反问

**禁止操作**：删除用户/Key、重置消费、修改 master key、变更模型权限。

---

## Step 1：解析需求

从 prompt 中提取：

| 字段 | 说明 | 示例 |
|------|------|------|
| operator_name | 操作请求人 | 赵开林 |
| target_user | 要操作的目标用户（邮箱、user_id 或 key 别名） | zhangsan@piaozone.com |
| action | 操作类型 | add_budget / query / list / extend |
| amount | 金额（USD），加额度时必需 | 20 |
| reason | 原因（可选） | 客户支持需要 |

如果 operator_name 不在管理员列表，回复：
> ⛔ 抱歉，您没有权限执行此操作。请联系管理员（赵开林）。

如果 target_user 缺失或歧义，使用 AskUserQuestion 反问。

---

## Step 2：查询当前状态（操作前必查）

无论是 add_budget 还是 query，都先查目标用户/Key 的当前状态：

```bash
# 按 user_id 查（推荐）
curl -s -X GET "$LITELLM_BASE_URL/user/info?user_id={target_user}" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"

# 按 key 别名查（如果 target_user 看起来像 key 别名）
curl -s -X GET "$LITELLM_BASE_URL/key/info?key={target_key}" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

提取关键字段：
- `max_budget`（USD）：总预算
- `spend`（USD）：已消费
- `available`：剩余 = max_budget - spend
- `expires`：过期时间

---

## Step 3：执行操作

### 3.1 加预算（add_budget）

**前置检查**（金额校验）：
1. 单次金额必须 ≤ `$LITELLM_MAX_BUDGET_PER_REQUEST`
2. 加完后总预算必须 ≤ `$LITELLM_MAX_TOTAL_BUDGET`
3. 任一超限 → 拒绝并提示："⚠️ 单次/总预算超限（限制：单次 $LITELLM_MAX_BUDGET_PER_REQUEST，总额 $LITELLM_MAX_TOTAL_BUDGET），需 OWNER 确认"

**执行**：

```bash
# 用户级加预算
NEW_BUDGET=$(echo "{current_max_budget} + {amount}" | bc)
curl -s -X POST "$LITELLM_BASE_URL/user/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"{target_user}\", \"max_budget\": $NEW_BUDGET}"
```

**Key 级加预算**（如目标是某个具体 key）：

```bash
NEW_BUDGET=$(echo "{current_max_budget} + {amount}" | bc)
curl -s -X POST "$LITELLM_BASE_URL/key/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"key\": \"{target_key}\", \"max_budget\": $NEW_BUDGET}"
```

### 3.2 查询消费（query）

直接调用 Step 2 的接口，格式化输出。

### 3.3 列出 key（list）

```bash
# 列出所有 key
curl -s -X GET "$LITELLM_BASE_URL/key/list?include_team_keys=true&size=100" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

### 3.4 延长有效期（extend）

```bash
NEW_EXPIRES="{当前时间 + N 天}"
curl -s -X POST "$LITELLM_BASE_URL/key/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d "{\"key\": \"{target_key}\", \"duration\": \"30d\"}"
```

---

## Step 4：审计日志（必须）

每次成功执行后，调用项目内审计接口记录：

```bash
curl -s -X POST "http://127.0.0.1:9123/api/tasks/{task_id}" \
  -H "Content-Type: application/json" \
  -d "{
    \"summary\": \"已为 {target_user} 增加预算 \\\$ {amount}（操作人 {operator_name}，原因: {reason}）\",
    \"full_report\": \"操作前: max_budget=\\\${old_budget}, spend=\\\${old_spend}\\n操作后: max_budget=\\\${new_budget}\\n原因: {reason}\"
  }"
```

---

## Step 5：回复用户

**加额度成功**：

```text
✅ 已为 {target_user} 增加预算 ${amount}
当前状态:
  max_budget: ${new_budget}
  已消费: ${spend}
  剩余: ${available}
操作人: {operator_name}
原因: {reason}
```

**查询**：

```text
📊 {target_user} 当前状态
  max_budget: ${max_budget}
  已消费: ${spend}
  剩余: ${available}
  过期: {expires_or_never}
```

**列表**：表格形式 Top 10，按消费倒序。

---

## 异常处理

| 场景 | 处理 |
|------|-----|
| 操作人不在管理员列表 | 拒绝，提示联系 `$LITELLM_ADMINS` 中的管理员 |
| 目标用户不存在 | 提示用户先创建 key |
| 单次金额超 `$LITELLM_MAX_BUDGET_PER_REQUEST` | 拆分多次或提示 OWNER 确认 |
| 总预算超 `$LITELLM_MAX_TOTAL_BUDGET` | 必须 AskUserQuestion 反问确认 |
| LiteLLM API 不可达 | 推送失败通知 |
