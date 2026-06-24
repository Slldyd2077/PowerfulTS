"""认证安全工具：密码哈希 (PBKDF2-HMAC-SHA256) + token 生成。

无外部依赖（仅标准库），存储格式与 Django 兼容：
`pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`
"""
from __future__ import annotations

import hashlib
import secrets

_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16
_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """生成密码哈希串。"""
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """恒定时间比对密码。stored 非法格式返回 False（不抛异常）。"""
    try:
        algo, iter_str, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError, TypeError):
        return False


def generate_token() -> str:
    """生成 URL 安全的随机 session token。"""
    return secrets.token_urlsafe(_TOKEN_BYTES)
