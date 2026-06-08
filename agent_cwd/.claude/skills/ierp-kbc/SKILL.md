---
name: ierp-kbc
description: KBC 出库单自动化处理 skill，支持三个操作：登录 iERP、导出销售出库单、导入 cosmic-pro。当用户说"登录 ierp/kbc"、"导出出库单"、"导出销售出库"、"导入 cosmic"、"导入 eop"、"跑一下出库单流程"、"帮我处理出库单"时必须使用此 skill。
---

# KBC 出库单自动化 Skill

支持三个独立操作，也可按顺序执行完整流程。

## 操作路由

根据用户意图选择操作：

| 用户说 | 执行操作 |
|--------|---------|
| 登录 ierp / 登录 kbc | 仅执行登录 |
| 导出出库单 / 导出销售出库 | 检查登录状态 → 导出 |
| 导入 cosmic / 导入 eop | 导入到 cosmic-pro |
| 跑一下出库单 / 处理出库单 | 导出 → 导入 → 通知 |

---

## 前置准备

所有脚本运行前，先进入 scripts 目录并激活虚拟环境：

```bash
cd <此SKILL.md所在目录>/scripts
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
```

确认 `config.json` 存在，否则提示用户参考 `references/config.example.json` 创建。

---

## 操作一：登录 iERP

### 步骤 1：检查本地 Cookie

```bash
python cookie_manager.py --check
```

- `COOKIE_STATUS: VALID` → 进入步骤 2 验证页面
- `COOKIE_STATUS: NOT_FOUND` / `ERROR` → 跳到步骤 3 扫码登录

### 步骤 2：用 Cookie 免登录验证

```
$B goto https://ierp.kingdee.com/ierp/
```

等待加载后截图，判断当前页面：
- **进入 iERP 首页**（能看到应用列表、工作台等）→ 登录有效，结束
- **跳到登录页**（看到"云之家登录"、二维码或账号输入框）→ 清除 Cookie，进入步骤 3：
  ```bash
  python cookie_manager.py --clear
  ```

### 步骤 3：扫码登录

打开登录页：
```
$B goto "https://passport.kingdee.com/passport/#/auth/oauth2/third_login?pck=ok&force_login=2&client_id=204758&response_type=code&redirect_uri=https%3A%2F%2Fierp.kingdee.com%2Fierp%2F%3Flanguage%3Dzh_CN%26sourcePage%3Dfalse&self_redirect=true"
```

截图观察页面：
- 看到账号密码输入框 → 需要切换到扫码登录，用文字定位点击云之家图标：
  ```
  $B click "云之家"
  ```
  等 3 秒后截图确认二维码出现。
- 已显示二维码 → 直接进入下一步。

**等待 iframe 渲染后截取二维码：**
```bash
python wait_for_login.py --capture-only --image /tmp/ierp_qrcode.png
```

发送云之家通知：
```bash
python notify_yzj.py --image /tmp/ierp_qrcode.png --retry 0
```

**等待扫码完成（脚本化轮询，不要手动循环）：**
```bash
python wait_for_login.py --image /tmp/ierp_qrcode.png
```

- 退出码 0 → 登录成功，进入保存 Cookie
- 退出码 1 → 超时或超次数，告知用户重试

### 步骤 4：保存 Cookie

```bash
$B cookies > /tmp/ierp_cookies_raw.json
python cookie_manager.py --save < /tmp/ierp_cookies_raw.json
```

---

## 操作二：导出销售出库单

**重要原则：** 所有页面操作优先用可见文字、aria-label 定位；遇到页面结构变化时，先截图观察再操作，不假设元素位置。

### 步骤 1：确认登录状态

```bash
python cookie_manager.py --check
```

- `VALID` → 用 Cookie 打开 iERP，截图确认是否在首页
- `NOT_FOUND` / `ERROR` → 先执行操作一完成登录

### 步骤 2：导入 Cookie 并打开 iERP

```bash
python cookie_manager.py --export > /tmp/ierp_cookies.json
$B goto https://ierp.kingdee.com/ierp/
$B cookie-import /tmp/ierp_cookies.json
$B reload
$B wait --networkidle
```

截图确认已进入首页，若跳到登录页则先执行操作一。

### 步骤 3：导航到销售出库处理页面

截图查看当前页面，**根据截图内容用文字定位**菜单入口，不要假设固定路径。

通常路径是：应用 → 库存管理 → 销售出库处理，但以截图为准：
```
$B snapshot -i
```
找到"应用"或"应用市场"入口后点击，再找"库存管理"，再找"销售出库处理"。每步都截图确认再操作。

若找不到预期菜单，截图并告知用户当前页面状态，请用户确认正确路径。

### 步骤 4：导出数据

进入销售出库处理列表后：

1. 点击"更多"按钮（用文字定位）：
   ```
   $B click "更多"
   ```
   截图确认下拉菜单已出现。

2. 点击"导出数据（按列表）"：
   ```
   $B click "导出数据（按列表）"
   ```

3. 等待确认对话框出现，点击"确定"：
   ```
   $B snapshot -i
   $B click "确定"
   ```

4. 等待导出完成并下载文件：
   ```bash
   python wait_for_download.py --output-dir /tmp/ierp_export/
   ```
   脚本轮询检测下载完成，返回文件路径。

### 步骤 5：过滤 Excel

```bash
python excel_filter.py --file <下载的文件路径>
```

过滤规则从 `config.json` 的 `excel_filter` 字段读取（`excluded_materials` 和 `exclude_contract_types`），无需改代码。

输出过滤后的文件路径，告知用户过滤了多少行。

---

## 操作三：导入 cosmic-pro

### 步骤 1：打开 cosmic-pro 登录页

从 `config.json` 读取 `eop.login_url`：
```
$B goto <eop.login_url>
$B wait --networkidle
```

截图查看当前页面。

### 步骤 2：登录

根据截图用文字/placeholder 定位输入框，不要假设固定选择器：
```
$B snapshot -i
$B fill "用户名" <eop.username>
$B press Tab
$B fill "密码" <eop.password>（或直接 type 到当前焦点）
$B click "登录"
```

若出现"继续登录"弹窗：
```
$B click "继续登录"
```

截图确认已进入首页。

### 步骤 3：导航到销售出库单

截图查看首页，根据可见内容找"销售出库单"入口：
```
$B snapshot -i
$B click "销售出库单"
```

若页面结构复杂找不到，用 snapshot 观察后再决定点击路径。

### 步骤 4：批量导入

1. 找到"批量导入"或"导入"按钮（文字定位）：
   ```
   $B snapshot -i
   $B click "批量导入"
   ```

2. 上传文件：
   ```
   $B upload "input[type='file']" <excel文件路径>
   ```

3. 点击确认：
   ```
   $B snapshot -i
   $B click "确定"
   ```

4. 等待导入完成，轮询检测成功提示：
   ```bash
   python wait_for_import.py
   ```

### 步骤 5：发送完成通知

```bash
python notify_yzj.py --text "$(date '+%Y-%m-%d') 出库单已导出，待执行" --complete
```

---

## 错误处理

- **登录失效（导出时发现）**：清除 Cookie，执行操作一完成重新登录，再回到操作二
- **页面结构变化**：截图后告知用户当前页面状态，请用户确认正确的操作路径
- **下载超时**：保存当前页面截图到 `scripts/logs/`，告知用户重试
- **导入失败**：截图保存到 `scripts/logs/`，输出错误信息

---

## 配置说明

所有业务参数在 `config.json` 中配置，页面结构变化时只需更新配置，不改代码：

- `ierp` — iERP 相关 URL
- `eop` — cosmic-pro 登录 URL、账号（敏感字段放 .env）
- `yzj` — 云之家通知配置（敏感字段放 .env）
- `excel_filter.excluded_materials` — 过滤掉的物料名称列表
- `excel_filter.exclude_contract_types` — 过滤掉的合同业务类型关键词
