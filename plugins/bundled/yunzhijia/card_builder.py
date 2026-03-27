"""卡片构建器 - 构建云之家图片卡片消息."""

import logging
from typing import List

logger = logging.getLogger(__name__)


class YunzhijiaCardBuilder:
    """云之家卡片消息构建器

    职责：
    1. 构建图片卡片消息载荷
    2. 处理多图片分卡片逻辑
    3. 生成卡片数据结构
    """

    def __init__(self, template_id: str, max_img_per_card: int):
        self.template_id = template_id
        self.max_img_per_card = max_img_per_card

    def build_card_payloads(self, img_urls: List[str], openid: str) -> List[dict]:
        """构建卡片消息载荷列表"""
        if not img_urls or not self.template_id:
            logger.warning("[CardBuilder] No images or template not configured")
            return []

        img_num = len(img_urls)
        card_num = (img_num + self.max_img_per_card - 1) // self.max_img_per_card

        payloads = []
        for i in range(card_num):
            data_content = self._build_data_content(img_urls, i)
            payload = {
                "msgType": 2,
                "param": {
                    "baseInfo": {
                        "templateId": self.template_id,
                        "dataContent": str(data_content)
                    }
                },
                "notifyParams": [{"type": "openIds", "values": [openid]}]
            }
            payloads.append(payload)

        logger.info(f"[CardBuilder] Built {card_num} card(s) for {img_num} image(s)")
        return payloads

    def _build_data_content(self, img_urls: List[str], card_index: int) -> dict:
        """构建单个卡片的 data_content"""
        data_content = {}
        start_idx = card_index * self.max_img_per_card
        end_idx = min(start_idx + self.max_img_per_card, len(img_urls))

        for j, idx in enumerate(range(start_idx, end_idx)):
            img_url = img_urls[idx]
            if j == 0:
                data_content["bigImageUrl"] = img_url
            else:
                data_content[f"bigImage{j}Url"] = img_url

        return data_content
