# GitLab 源码动态定位策略

## 一、从 fields.project 推断仓库

日志中 `fields.project` 即服务名（如 `smkp`）。按以下顺序查找仓库：

**方式 A（优先）：查映射表**

先读取 [references/service-repo-map.md](references/service-repo-map.md)，在表中精确匹配 `fields.project`，直接获得 `project_id`。
这是最可靠的方式，因为日志服务名与 GitLab 仓库名可能不一致（如 `smkp` → `kingdee/bill-smkp`）。

**方式 B（降级）：搜索仓库**

映射表未命中时，调用搜索：
```
mcp__gitlab__search_repositories(search="{fields.project}")
```
取名称最接近的结果，获得完整 `project_id`（格式：`namespace/repo-name`）。
**注意**：`project_id` 必须使用搜索结果中的完整路径，不能直接用服务名。

**无法定位时**：跳过本步骤，不影响日志分析结论输出。

---

## 二、获取本地源码（必须 clone，禁止逐文件 API 拉取）

> **强制规范**：查看任何项目源码，必须将整个仓库 clone 到本地后再检索。**严禁**使用 `mcp__gitlab__get_file_contents` 等 GitLab API 逐文件拉取。

获得 `project_id` 后，按以下逻辑操作：

```bash
LOCAL_DIR="/tmp/gitlab/src/{repo-name}"

# 本地已有 → 拉取最新代码
if [ -d "$LOCAL_DIR/.git" ]; then
  git -C "$LOCAL_DIR" pull
# 本地没有 → 完整 clone
else
  git clone "https://git.kingdee.com/{namespace/repo-name}.git" "$LOCAL_DIR"
fi
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
