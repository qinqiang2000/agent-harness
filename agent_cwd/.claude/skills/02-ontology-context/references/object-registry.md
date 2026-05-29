# 对象注册表

> 本体文件通过已配置的 ontology MCP 服务获取，skill 直接调用 MCP 工具即可。

## 对象清单

| 对象名称              | 缩写      | 中文名    | 特性ID前缀 |
| ----------------- | ------- | ------ | ------ |
| invoice-data      | invd    | 销项发票数据 | F-I-D  |
| credit-note-apply | cnapp   | 红字确认单  | F-I-C  |
| invoice-file      | invf    | 电子发票文件 | F-I-F  |
| billing-request   | billreq | 开票申请单  | F-I-B  |
| party             | party   | 参与方    | F-I-P  |

## 每个对象目录下的标准文件名模式

```
{abbr}_01_Properties.md                          — 属性表（状态层/业务层/扩展层）
{abbr}_01_Properties-design-notes.md             — 属性分类与设计原则
{abbr}_02_LinkTypes.md                           — 对象间链接类型
{abbr}_03_ValueSets.md                           — 状态枚举 + 状态流转图
{abbr}_04_ActionTypes.md                         — 动作速查表 + 动作详情
{abbr}_05_Functions/{abbr}_05.0_Functions.md      — 函数资产总览（L1/L2/L3/L4）
{abbr}_05_Functions/{abbr}_05.1_{Profile}_RulePackage.md  — Profile 规则包
```

> 注意：部分对象的函数总览文件名可能为 `{abbr}_05.0_FunctionTypes.md`，获取时需兼容。

## 动作序号提取规则

从 ACT-XX 中提取数字部分作为特性 ID 序号：
- `ACT-01` → 序号 `01` → 特性 ID 如 `F-I-D01`
- `ACT-04` → 序号 `04` → 特性 ID 如 `F-I-D04`
- `ACT-10` → 序号 `10` → 特性 ID 如 `F-I-D10`
