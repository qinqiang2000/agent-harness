# 接口代码查阅流程

> 当用户描述涉及某个接口（如"查验接口"、"开票接口"）时，按此流程定位接口对应的源码位置。
> 这是一个**代码查阅流程**，不是问题诊断流程——目标是找到接口的实现代码，帮助用户理解接口处理逻辑。

---

## 触发条件

同时满足以下两个信号：
1. **业务关键词**：用户描述含"查验"、"开票"、"收票"、"采集"、"鉴权"等业务名称
2. **接口信号**：用户明确提及"接口"、"API"、"路径"、"endpoint"，或描述涉及"调用流程"、"处理逻辑"、"代码在哪"等

且 `data/kb/接口文档/` 目录存在（已完成 Apifox 同步）。

---

## Step A：从 KB 匹配接口路径

1. 列出 `data/kb/接口文档/` 目录下所有子目录和 `.md` 文件（排除 `_sync_meta.json`）
2. 按以下优先级选择文件读取（最多 2 个）：
   - 文件名或目录名包含用户描述的业务关键词（如"开票"、"收票"、"查验"）→ 优先读取
   - 若相关文件超过 2 个，按文件名与关键词的匹配度排序取前 2 个
3. 在选中的文件中，按接口名称、路径、描述做语义匹配，找出相关接口候选

**匹配到多个接口时**：列出所有候选接口的名称和路径，**反问用户确认具体是哪个接口**，等用户明确后再继续后续步骤。不要告知用户接口文档所在的具体目录路径。

**只匹配到一个接口时**：直接提取该接口的 **HTTP 方法** 和 **路径**（如 `POST /m3/bill/invoice/issue`），继续后续步骤。

**未匹配到接口时**：告知用户未找到相关接口，询问是否提供完整接口路径后继续。

---

## Step B：通过网关路由找到服务名

1. 读取 [references/gateway-routes.md](gateway-routes.md)
2. 用接口路径的**前缀**匹配路由表（注意路由按顺序匹配，`/**` 是兜底路由）
3. 得到服务名（如 `/m3/**` → `api-invoice-frame`）

**匹配规则**：
- 路径前缀精确匹配优先（如 `/etax-bill/fpdk/**` 优先于 `/etax-bill/**`）
- 多个前缀命中同一路由时，取最长前缀匹配
- 若只命中兜底路由 `/**`（服务 `erp`），需告知用户该路径可能未在网关配置中，建议确认路径是否正确

---

## Step C：通过服务名找到 GitLab 仓库

按 [references/gitlab-lookup.md](gitlab-lookup.md) 的流程执行：
1. 读取 [references/service-repo-map.md](service-repo-map.md)，用服务名精确匹配，获取 `project_id`
2. 映射表未命中时，用 `mcp__gitlab__search_repositories(search="{服务名}")` 搜索
3. 获得 `project_id` 后，clone 仓库到本地

---

## Step D：在源码中定位接口实现

clone 成功后，在本地仓库中搜索接口路径对应的 Controller：

```bash
# 搜索接口路径（去掉通配符前缀，如 /m3 → 搜索路径后半段）
Grep(pattern="bill/invoice/issue", path="/tmp/gitlab/src/{repo-name}", glob="*.java")

# 或搜索 @RequestMapping / @PostMapping 注解
Grep(pattern='@(Post|Get|Put|Delete)Mapping.*invoice.*issue', path="/tmp/gitlab/src/{repo-name}", glob="*.java")
```

找到 Controller 后：
1. 读取 Controller 方法，了解入参和调用链
2. 顺着调用链找到核心 Service 方法
3. 输出接口处理流程

---

## 输出格式

```
【接口定位结果】
接口：{method} {path}
服务：{service-name}
仓库：{gitlab-project-id}

【处理流程】
1. {ControllerClass}.{method}()  → 入口，接收参数：{params}
2. {ServiceClass}.{method}()     → 核心业务逻辑
3. {下游调用}                    → 调用外部服务/数据库

【关键代码位置】
- {ClassName}.java:{行号}  {关键逻辑描述}
```

---

## 注意事项

- **禁止自行推断接口路径**：路径必须来自 KB 文件或用户明确提供
- **禁止修改接口路径**（如补全版本号、修改参数格式）
- **禁止透露 KB 目录路径**：不要向用户展示接口文档所在的具体目录结构
- **多个候选必须先确认**：匹配到多个接口时，必须列出候选让用户选择，不得自行选择其中一个继续
- clone 失败时，告知用户仓库信息（服务名、project_id），建议用户自行查看
