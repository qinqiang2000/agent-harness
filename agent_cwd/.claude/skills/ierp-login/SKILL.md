---
name: ierp-login
description: 登录金蝶 iERP 系统（https://ierp.kingdee.com/ierp/）。通过 browse skill 驱动浏览器，自动检测二维码并通过云之家通知指定人员扫码完成登录，支持 Cookie 缓存避免重复扫码。当用户说"登录 ierp"、"打开金蝶"、"ierp 登录"、"帮我登一下 ierp"，或在执行任何 ierp 操作前需要登录时，必须使用此 skill。
---

# iERP 登录 Skill

此 skill 完成金蝶 iERP 的扫码登录，流程如下：

## 前置检查

所有脚本运行前，先进入 skill 的 scripts 目录并激活虚拟环境：
```bash
cd <此SKILL.md所在目录>/scripts
# 若 .venv 不存在，先初始化
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
```

确认 `config.json` 存在，否则提示用户参考 `references/config.example.json` 创建。

## 步骤 1：检查本地是否有 Cookie 文件

```bash
python cookie_manager.py --check
```

- 输出 `COOKIE_STATUS: VALID` → 本地有 Cookie，进入步骤 2 用页面验证是否真实有效
- 输出 `COOKIE_STATUS: NOT_FOUND` → 本地无 Cookie，跳到步骤 3 扫码登录
- 输出 `COOKIE_STATUS: ERROR` → Cookie 文件损坏，执行 `python cookie_manager.py --clear` 后跳到步骤 3

## 步骤 2：用 Cookie 免登录验证

使用 browse skill：
1. 导出 Cookie：`python cookie_manager.py --export > /tmp/ierp_cookies.json`
2. 打开 iERP：`$B goto https://ierp.kingdee.com/ierp/`
3. 导入 Cookie：`$B cookie-import /tmp/ierp_cookies.json`
4. 刷新页面：`$B reload`
5. 等待加载：`$B wait --networkidle`
6. 截图查看当前页面，判断是否已进入 iERP 首页（非登录页）
   - 已进入首页 → 登录成功，结束
   - 仍是登录页 → 清除 Cookie（`python cookie_manager.py --clear`），进入步骤 3

## 步骤 3：扫码登录

使用 browse skill 打开登录页：
```
$B goto https://passport.kingdee.com/passport/#/auth/oauth2/third_login?pck=ok&force_login=2&client_id=204758&response_type=code&redirect_uri=https%3A%2F%2Fierp.kingdee.com%2Fierp%2F%3Flanguage%3Dzh_CN%26sourcePage%3Dfalse&self_redirect=true
```

等待页面加载后截图，观察页面状态：
- 如果看到账号密码输入框（手机号/密码输入框），说明默认显示了账号登录页。需要切换到扫码登录，**优先通过文本或 aria-label 定位云之家图标**（不要用坐标，坐标随分辨率变化会失效）：
  ```
  $B click "[aria-label='云之家']"
  ```
  若 aria-label 定位失败，可尝试点击页面底部登录方式区域内包含"云之家"文字的元素：
  ```
  $B click "云之家"
  ```
  等待 3 秒后截图确认二维码已出现。
- 如果已显示二维码，直接进入步骤 4。

**重要：** 二维码在 `iframe#qr-code` 内部渲染，主页面无法直接检测其状态。

## 步骤 4：截取并发送二维码

`wait_for_login.py` 会自动处理截图，这里只需要完成首次截图和通知：

1. 动态定位 iframe 边界后截取二维码区域：
   ```bash
   # 通过 JS 获取 iframe 位置，动态计算 clip 参数
   $B js "JSON.stringify(document.querySelector('iframe#qr-code')?.getBoundingClientRect() || {})"
   # 根据返回的 {left,top,width,height} 计算截图区域，截图保存
   $B screenshot /tmp/ierp_qrcode.png --clip <left-10>,<top-10>,<width+20>,<height+20>
   # 若 iframe 定位失败，降级使用固定区域
   $B screenshot /tmp/ierp_qrcode.png --clip 950,100,280,380
   ```
2. 发送云之家通知：
   ```bash
   python notify_yzj.py --image /tmp/ierp_qrcode.png --retry 0
   ```
3. 告知用户："已通过云之家发送二维码，请扫码登录"

## 步骤 5：等待扫码（脚本化轮询）

直接运行等待脚本，不要手动循环：
```bash
python wait_for_login.py
```

脚本内部每 3 秒检测一次登录状态，每 30 秒自动刷新二维码并重新通知，超时和刷新上限从 `config.json` 读取（`scan_timeout` 默认 180 秒，`max_qrcode_retry` 默认 5 次）。

- 脚本退出码 0 → 登录成功，进入步骤 6
- 脚本退出码 1 → 超时或超过刷新上限，告知用户重试

## 步骤 6：保存 Cookie

登录成功后：
1. 等待页面完全加载：`$B wait --networkidle`
2. 获取当前 Cookie 并保存到文件（避免 shell 管道特殊字符问题）：
   ```bash
   $B cookies > /tmp/ierp_cookies_raw.json
   python cookie_manager.py --save < /tmp/ierp_cookies_raw.json
   ```

## 步骤 7：完成

输出登录成功信息：
```
✅ iERP 登录成功
   Cookie 有效期：<expire_time>
```

## 错误处理

- **云之家通知失败**：打印警告但继续等待扫码，不中断流程

- **browse 操作失败**：将当前页面截图保存到 `scripts/logs/` 供排查，然后输出错误信息：
  ```bash
  mkdir -p <此SKILL.md所在目录>/scripts/logs
  $B screenshot <此SKILL.md所在目录>/scripts/logs/error_$(date +%Y%m%d_%H%M%S).png
  ```

- **Cookie 检查报 ERROR**：说明 Cookie 文件损坏，直接清除后走扫码流程：
  ```bash
  python cookie_manager.py --clear
  ```

- **二维码刷新超限或超时**：`wait_for_login.py` 会输出明确错误信息，提示用户手动检查网络或重新运行 skill
