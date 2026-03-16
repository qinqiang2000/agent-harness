# 收票诊断速查表

## 1. 发票状态码

| 状态码 | 含义 |
|---|---|
| 0 | 正常 |
| 2 | 作废 |
| 3 | 红冲 |
| 4 | 异常 |
| 5 | 蓝冲 |
| 7 | 部分红冲 |
| 8 | 全额红冲 |

## 2. 入账状态码

| 状态码 | 含义 |
|---|---|
| 01 | 未入账 |
| 02 | 已入账 |
| 03 | 已勾选 |
| 06 | 已退回 |

## 3. RPA 错误码

| 错误码 | 含义 | 处理建议 |
|---|---|---|
| 1307 | 处理中可重试（含 429 限流） | 可重试 |
| 1100 | 不可恢复错误 | 不可重试，需人工介入 |
| 1706 | 任务失败 |
| 1300 | 参数错误 | 检查请求参数 |

## 4. 查验缓存 Key 格式

```
invoice_verification_v4:{type}:{code}:{number}:{date}:{verCode}:{amount}
```

- **不含** clientId
- 常见问题：末位截断导致 key 不匹配（如 `checkData:261420000001211879265` vs `checkData:26142000000121187926`）

## 5. isDxCheck 供应商路由

| 值 | 供应商 |
|---|---|
| 1 | 大象慧云 |
| 4 | 长软（主要） |
| 5 | 公有云 |
| 6 | 账无忧 |
| 7 | 微乐 |
| 8 | 宁波港 |
| 9 | 大象慧云航信 |
| 默认 | 互金 |

## 6. 标准版 vs 重构版识别

| 前缀 | 版本 |
|---|---|
| `fpy-` | 重构版 |
| `api-invoice-` | 标准版 |

## 7. 收票调用链速查

| 场景 | 调用链 |
|---|---|
| 旗舰版 | api-invoice-frame → 标准版核心服务 |
| EAS / 苍穹 / 星空 | api-fpzs → api-invoice-check / api-invoice-recognition / api-invoice-collector |
| 重构版 | fpy-gateway → fpy-isv → fpy-base-query |
| RPA / 税局下票 | api-invoice-collector（包路径 `com.kingdee.service.etax`） |
