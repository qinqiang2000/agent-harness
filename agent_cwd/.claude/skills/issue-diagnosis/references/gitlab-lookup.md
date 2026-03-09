# GitLab 源码动态定位策略

## 一、从 fields.project 推断仓库

日志中 `fields.project` 即服务名（如 `api-elc-invoice-lqpt`）。按以下顺序查找仓库：

**方式 A：搜索仓库**
```
mcp__gitlab__search_repositories(search="{fields.project}")
```
取第一个名称完全匹配的结果，获得完整 `project_id`（格式：`namespace/repo-name`）。

**方式 B：若 kb/faq.md 顶部有服务映射表**
优先使用映射表中的配置路径，跳过搜索。

**无法定位时**：跳过本步骤，不影响日志分析结论输出。

---

## 二、类名转文件路径

Java 类名 `com.kingdee.xxx.ClassName` → `src/main/java/com/kingdee/xxx/ClassName.java`

去掉 `-数字` 线程后缀：`ClassName-1` → `ClassName`

---

## 三、选择目标类（最多 3 个）

优先级：**报错类（最后一条 ERROR/WARN）> 调用者类（报错类前一步）> 入口类（callChain 第一条）**

---

## 四、并行拉取源码

同一服务的多个类同时拉取：
```
mcp__gitlab__get_file_contents(project_id="{namespace/repo}", file_path="{文件路径}", ref="main")
```

- 文件 404 → 尝试 `master` 分支，仍 404 则跳过该类
- 所有类均 404 → 跳过源码分析，仅输出日志结论

---

## 五、调用链还原输出格式

```
【调用链分析】
请求处理流程：
  1. EntryClass.method()     → 处理起点
  2. ServiceClass.handle()   → 核心业务处理
  3. ClientClass.invoke()    → ❌ HTTP 500，抛出异常

根因（结合源码）：ClientClass.java:87 收到非 2xx 状态码直接抛出异常，未做重试。
```

将结论以 `[源码]` 前缀补充进 `possibleCause` 和 `suggestedSolution`。
