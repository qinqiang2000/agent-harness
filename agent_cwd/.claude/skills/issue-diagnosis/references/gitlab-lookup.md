# GitLab 源码动态定位策略

## 一、从 fields.project 推断仓库

日志中 `project` 即服务名（如 `smkp`）。按以下顺序查找仓库：

**方式 A（优先）：查映射表**

先读取 [references/service-repo-map.md](references/service-repo-map.md)，在表中精确匹配 `fields.project`，直接获得 `project_id`。
这是最可靠的方式，因为日志服务名与 GitLab 仓库名可能不一致（如 `smkp` → `kingdee/bill-smkp`）。

**方式 B（降级）：搜索仓库**

映射表未命中时，调用搜索：
```
mcp__gitlab__search_repositories(search="{fields.project 的值}")
```
**注意**：search 参数必须传 `fields.project` 的值（服务名），禁止传类名、方法名或其他关键词。
取名称最接近的结果，获得完整 `project_id`（格式：`namespace/repo-name`）。

**无法定位时**：跳过本步骤，不影响日志分析结论输出。

---

## 二、获取本地源码（必须 clone，禁止逐文件 API 拉取）

> **强制规范**：查看任何项目源码，必须将整个仓库 clone 到本地后再检索。**严禁**使用 `mcp__gitlab__get_file_contents`、`mcp__gitlab__search_repositories` 等 GitLab API 逐文件拉取或搜索源码内容。

获得 `project_id` 后，用单条 Bash 命令完成 clone 或 pull：

```bash
LOCAL_DIR="/tmp/gitlab/src/{repo-name}" && ([ -d "$LOCAL_DIR/.git" ] && git -C "$LOCAL_DIR" pull || git clone "https://token:$GITLAB_TOKEN@test-master.piaozone.com/git/{namespace/repo-name}.git" "$LOCAL_DIR")
```

- clone / pull 成功后，所有源码检索均在本地目录进行
- 若 clone 失败（权限不足、网络问题）→ 跳过源码分析，直接凭日志给出结论，不等待用户追问

---

## 三、本地源码检索

clone 成功后，用 Grep 搜索目标类：

```bash
# 按类名搜索
Grep(pattern="class {ClassName}", path="/tmp/gitlab/src/{repo-name}")

# 按方法名搜索
Grep(pattern="{methodName}", path="/tmp/gitlab/src/{repo-name}", glob="*.java")
```

优先级：**报错类（最后一条 ERROR/WARN）> 调用者类（报错类前一步）> 入口类（callChain 第一条）**

找到文件后用 Read 读取具体内容，重点关注日志中报错的行号附近逻辑。

**源码定位的目标不是找到报错行就结束，而是要回答：**
- 报错行在做什么操作（如 substring、类型转换、空值访问）？
- 这个操作依赖什么输入数据（方法参数、外部返回值、配置值）？
- 结合日志中的实际数据，是哪个具体的输入值触发了异常？
- 根因是调用方传了非预期数据，还是被调用方返回了非预期格式，还是代码本身缺少防御？

**只有回答了"是什么数据/条件导致走到这里"，才算完成根因定位。**

---

## 四、调用链还原输出格式

```
【调用链分析】
请求处理流程：
  1. EntryClass.method()     → 处理起点
  2. ServiceClass.handle()   → 核心业务处理
  3. ClientClass.invoke()    → ❌ HTTP 500，抛出异常

根因（结合源码）：ClientClass.java:87 收到非 2xx 状态码直接抛出异常，未做重试。
```

将结论以 `[源码]` 前缀补充进 `possibleCause` 和 `suggestedSolution`。
