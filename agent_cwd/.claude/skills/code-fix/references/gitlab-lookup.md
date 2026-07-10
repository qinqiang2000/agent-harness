# GitLab 源码定位策略

## 一、从 project 推断仓库

日志中 `project` 即服务名（如 `smkp`）。读取 [service-repo-map.md](service-repo-map.md)，精确匹配 `project` 字段，获得 `project_id` 和 `repo-name`。

映射表未命中时，跳过源码分析，直接凭日志给出结论，不猜测仓库路径。

---

## 二、获取本地源码（clone 或 pull）

代码存放在 `{REPO_DIR}/{repo-name}`，**不删除，下次同项目直接 pull 最新代码**。

获得 `project_id` 后，用单条 Bash 命令完成 clone 或 pull。**必须原样使用以下模板，禁止修改 URL 格式（特别是不得省略 `token:$GITLAB_TOKEN@` 部分，否则会因认证失败导致 clone 失败）**：

```bash
LOCAL_DIR="{REPO_DIR}/{repo-name}" && \
GITLAB_BASE="${GITLAB_BASE_URL:-http://123.207.158.7:5000/ai-agent/git}" && \
([ -d "$LOCAL_DIR/.git" ] && git -C "$LOCAL_DIR" pull || \
 git clone "$(echo $GITLAB_BASE | sed 's|://|://token:'"$GITLAB_TOKEN"'@|')/{namespace/repo-name}.git" "$LOCAL_DIR")
```

其中：
- `{REPO_DIR}` = `$BILLING_REPO_DIR` 环境变量值，未设置时默认 `/tmp/billing/repos/`
- `{repo-name}` = service-repo-map.md 中该服务对应的仓库短名（如 `api-fpzs`）
- `{namespace/repo-name}` = service-repo-map.md 中的完整 `project_id`（如 `piaozone/input/api-fpzs`）

clone / pull 成功后，所有源码检索均在本地目录进行。

若 clone 失败（权限不足、网络问题）→ 跳过源码分析，直接凭日志给出结论，不等待用户追问。

---

## 三、本地源码检索

clone 成功后，用 grep 搜索目标类：

```bash
# 按类名搜索
grep -r "class {ClassName}" {REPO_DIR}/{repo-name} --include="*.java" -l

# 按方法名搜索
grep -r "{methodName}" {REPO_DIR}/{repo-name} --include="*.java" -l
```

优先级：**报错类（最后一条 ERROR/WARN）> 调用者类（报错类前一步）> 入口类（callChain 第一条）**

找到文件后读取具体内容，重点关注日志中报错的行号附近逻辑。

---

## 四、联合分析目标

源码定位的目标是联合日志数据回答：
1. 报错行在做什么操作（如 substring、类型转换、空值访问）？
2. 这个操作依赖什么输入数据（方法参数、外部返回值、配置值）？
3. 结合日志中的实际数据，是哪个具体的输入值触发了异常？
4. 根因是调用方传了非预期数据，还是被调用方返回了非预期格式，还是代码本身缺少防御？

**只有回答了"是什么数据/条件导致走到这里"，才算完成根因定位。**

---

## 五、调用链输出格式

```
【调用链分析】
请求处理流程：
  1. EntryClass.method()     → 处理起点
  2. ServiceClass.handle()   → 核心业务处理
  3. ClientClass.invoke()    → ❌ HTTP 500，抛出异常

根因（结合源码）：ClientClass.java:87 收到非 2xx 状态码直接抛出异常，未做重试。
```

将结论补充进【证据】和【解决建议】。
