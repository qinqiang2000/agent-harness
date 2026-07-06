# 星瀚源码 KB 索引 + Wiki 映射表

## 预编译 KB 路径

由 `scripts/build_xinghan_kb.sh` 预先生成（Vineflower 反编译），skill 运行时直接读取，禁止实时反编译：

```
data/source/xinghan/
├── 8.0.4/
├── 8.0.9/
└── 8.0.14/    ← 当前最大版本号即最新版本
```

每个版本目录结构：
```
{版本号}/
├── index.md             ← 类名 → 文件路径索引
├── imc-bdm-common/
│   └── kd/imc/bdm/common/helper/
│       ├── BotpHelper.java
│       ├── DrawerStrategyHelper.java
│       └── ...
├── imc-bdm-formplugin/
├── imc-sim-service/     ← 含 BillMatchHelper.java
└── ...
```

列出已有版本（版本号为目录名，数字越大越新）：
```
Glob(pattern="data/source/xinghan/*/index.md")
```

---

## Java 源码分析要点

Vineflower 反编译输出的是接近原始代码的 Java 源文件，分析时关注：

| 模式 | 含义 |
|------|------|
| `collection.get(i - 1)` 或 `list.get(index - 1)` | 下标 `i-1`，**`i=0` 时越界** |
| `for (int i = 0; ...)` + 内部 `get(i - 1)` | 循环从 0 开始但访问前一行，第一行必越界 |
| `SomeEnum.XXX.getCode().equals(value)` | 枚举分支，直接读枚举常量名（如 `CURRENT_USER`）即可理解业务含义 |
| `dynamicObject.getString("fieldName")` | 读取业务字段，`fieldName` 即数据库列的 key |
| `dynamicObject.set("fieldName", value)` | 写入业务字段 |
| 静态 Helper 调用如 `XxxHelper.dealXxx(...)` | 跨类调用，找对应类的源文件继续读 |

---

## Product-Wiki 根目录

软链路径（由 `scripts/setup_knowledge.sh` 初始化）：
```
data/Product-Wiki/
├── wiki/
│   ├── entities/   ← 实体文档（优先查）
│   ├── flows/      ← 全链路流程文档
│   └── index.md
└── raw/
    └── 星瀚开票/
        └── simdoc/ ← 原始功能文档（含调用链表格）
```

---

## 业务关键词 → Wiki 文件映射

| 关键词 | 优先查阅路径 |
|--------|------------|
| 开票申请单、BOTP、BOTP下推 | `data/Product-Wiki/wiki/entities/开票-开票申请单.md` → `data/Product-Wiki/raw/星瀚开票/simdoc/BOTP下推开票申请单匹配功能文档.md` |
| 开票人、开票方、drawer、DrawerStrategy | `data/Product-Wiki/raw/星瀚开票/simdoc/metadata/sim_drawer_setting(开票方实体).md` |
| 拆分、合并、BotpHelper、closeBills | `data/Product-Wiki/wiki/entities/开票-开票申请单.md` → `data/Product-Wiki/wiki/flows/开票-开票全链路.md` |
| 红字确认单、红冲、负数申请单 | `data/Product-Wiki/wiki/entities/开票-红字确认单.md` |
| 数电发票、全电发票 | `data/Product-Wiki/wiki/entities/开票-数电发票.md` |
| 开票回调、回写 | `data/Product-Wiki/wiki/entities/开票-开票回调.md` |
| 特殊票种 | `data/Product-Wiki/wiki/entities/开票-特殊票种处理.md` |
| 开票全链路、完整流程 | `data/Product-Wiki/wiki/flows/开票-开票全链路.md` |

未在映射表中 → 用 Glob 搜索：
```
Glob(pattern="data/Product-Wiki/wiki/entities/*{关键词}*.md")
Glob(pattern="data/Product-Wiki/raw/**/*{关键词}*.md")
```
