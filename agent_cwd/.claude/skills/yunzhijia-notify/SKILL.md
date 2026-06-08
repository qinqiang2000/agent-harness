---
name: yunzhijia-notify
description: 通过云之家公共号发送消息给指定人员。支持文字消息和图片消息两种类型。当用户说"发云之家消息"、"通知云之家"、"发个云之家"、"yzj 通知"、"发消息给 XXX"、"用云之家发"，或其他 skill 需要发送云之家通知时，必须使用此 skill。
---

# 云之家通知 Skill

通过云之家公共号 API 发送消息，支持文字和图片两种消息类型。

## 前置准备

进入 scripts 目录并激活虚拟环境：

```bash
cd <此SKILL.md所在目录>/scripts
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
```

确认 `config.json` 存在，否则提示用户参考 `references/config.example.json` 创建。

---

## 发送文字消息

```bash
python notify.py --text "消息内容"
```

可选参数：
- `--complete`：发送给 `complete_user_ids`（流程完成通知接收人），默认发给 `user_ids`
- `--title "标题"`：消息标题（文字消息不支持标题，忽略此参数）

示例：
```bash
python notify.py --text "2024-05-14 出库单已导出，待执行"
python notify.py --text "流程已完成" --complete
```

---

## 发送图片消息

```bash
python notify.py --image <图片路径> [--title "消息标题"] [--text "附加说明"]
```

图片会自动缩小后居中放在白色背景上，避免云之家卡片展示时裁剪。

示例：
```bash
python notify.py --image /tmp/qrcode.png --title "请扫码" --text "请用手机扫描二维码"
python notify.py --image /tmp/screenshot.png --title "页面截图"
```

---

## 配置说明

配置文件 `scripts/config.json`（参考 `references/config.example.json`）：

```json
{
  "yzj": {
    "pubsend_url": "https://yunzhijia.com/pubacc/pubsendV2",
    "company_id": "企业ID",
    "pub_id": "公共号ID（XT-xxxx 格式）",
    "pub_secret": "",
    "session_cookie": "",
    "user_ids": ["默认接收人 OpenID"],
    "complete_user_ids": ["完成通知接收人 OpenID"]
  }
}
```

敏感字段（`pub_secret`、`session_cookie`）优先从 `scripts/.env` 读取：

```
YZJ_PUB_SECRET=your_secret
YZJ_SESSION_COOKIE=PLAY_SESSION="..."
```

---

## 错误处理

- 配置不完整：输出具体缺失字段，提示用户检查 `config.json` 和 `.env`
- 发送失败：输出云之家返回的错误码，检查 `pub_secret` 是否正确、`session_cookie` 是否过期
