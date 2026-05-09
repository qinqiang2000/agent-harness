"""企业微信消息加解密（AES-256-CBC + XML）."""

import base64
import hashlib
import hmac
import os
import struct
import time
import xml.etree.ElementTree as ET
from Crypto.Cipher import AES


class WecomCrypto:
    """企业微信消息加解密工具。

    参考：https://developer.work.weixin.qq.com/document/path/90968
    """

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        self.token = token
        self.corp_id = corp_id
        # EncodingAESKey 是 43 位 Base64，解码后得到 32 字节 AES key
        self.aes_key = base64.b64decode(encoding_aes_key + "=")

    def verify_signature(self, msg_signature: str, timestamp: str, nonce: str, echostr: str = "") -> bool:
        """验证消息签名."""
        expected = self._make_signature(timestamp, nonce, echostr)
        return hmac.compare_digest(expected, msg_signature)

    def decrypt_message(self, xml_body: str) -> tuple[str, str]:
        """解密企业微信消息体，返回 (明文消息XML, receiver_id)."""
        root = ET.fromstring(xml_body)
        encrypt = root.findtext("Encrypt")
        if not encrypt:
            raise ValueError("XML 中缺少 Encrypt 字段")
        plaintext, receiver_id = self._decrypt(encrypt)
        return plaintext, receiver_id

    def encrypt_message(self, reply_xml: str, timestamp: str, nonce: str) -> str:
        """加密回复消息，返回完整的加密 XML 字符串."""
        encrypted = self._encrypt(reply_xml)
        signature = self._make_signature(timestamp, nonce, encrypted)
        return (
            "<xml>"
            f"<Encrypt><![CDATA[{encrypted}]]></Encrypt>"
            f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>"
            f"<TimeStamp>{timestamp}</TimeStamp>"
            f"<Nonce><![CDATA[{nonce}]]></Nonce>"
            "</xml>"
        )

    def _make_signature(self, timestamp: str, nonce: str, data: str = "") -> str:
        parts = sorted([self.token, timestamp, nonce, data])
        return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()

    def _decrypt(self, encrypted: str) -> tuple[str, str]:
        ciphertext = base64.b64decode(encrypted)
        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_key[:16])
        plaintext = cipher.decrypt(ciphertext)
        # 去除 PKCS7 padding
        pad_len = plaintext[-1]
        plaintext = plaintext[:-pad_len]
        # 格式：16字节随机串 + 4字节消息长度（网络字节序）+ 消息内容 + corp_id
        content = plaintext[16:]
        msg_len = struct.unpack(">I", content[:4])[0]
        msg_content = content[4: 4 + msg_len].decode("utf-8")
        receiver_id = content[4 + msg_len:].decode("utf-8")
        return msg_content, receiver_id

    def _encrypt(self, plaintext: str) -> str:
        random_bytes = os.urandom(16)
        content = plaintext.encode("utf-8")
        msg_len = struct.pack(">I", len(content))
        corp_id = self.corp_id.encode("utf-8")
        raw = random_bytes + msg_len + content + corp_id
        # PKCS7 padding（块大小 32）
        block_size = 32
        pad_len = block_size - len(raw) % block_size
        raw += bytes([pad_len]) * pad_len
        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_key[:16])
        return base64.b64encode(cipher.encrypt(raw)).decode("utf-8")
