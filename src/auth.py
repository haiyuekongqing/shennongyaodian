"""
管理员认证模块
密码使用 SHA-256 + 随机盐加密存储。

设置管理员密码：
  python scripts/setup_admin.py
"""
import os
import uuid
import time
import hashlib
import secrets
import logging
from typing import Optional, Dict, Tuple

from src.config.settings import settings

logger = logging.getLogger(__name__)

TOKEN_EXPIRE_SECONDS = 86400  # 24 小时
ADMIN_ENV_USERNAME = "ADMIN_USERNAME"
ADMIN_ENV_PASSWORD_HASH = "ADMIN_PASSWORD_HASH"
ADMIN_ENV_PASSWORD_SALT = "ADMIN_PASSWORD_SALT"


def _generate_salt(length: int = 16) -> str:
    return secrets.token_hex(length)


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _verify_password(password: str, salt: str, stored_hash: str) -> bool:
    return _hash_password(password, salt) == stored_hash


# ── 环境变量管理 ─────────────────────────────────

def _load_env_file() -> Dict[str, str]:
    """
    加载认证配置。优先读环境变量（Docker Compose 已注入），再读 .env 文件。
    """
    result = {}

    # 从环境变量读取（Docker Compose 注入）
    for key in (ADMIN_ENV_USERNAME, ADMIN_ENV_PASSWORD_SALT, ADMIN_ENV_PASSWORD_HASH):
        val = os.environ.get(key)
        if val:
            result[key] = val.strip("\"'")  # Docker Compose 注入的变量带引号，需要去掉

    # 如果环境变量中已有完整配置，直接返回
    if ADMIN_ENV_PASSWORD_HASH in result and ADMIN_ENV_PASSWORD_SALT in result:
        return result

    # 从 .env 文件读取（本地开发环境）
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    result[key.strip()] = value.strip().strip("\"'")

    return result


def _save_env_var(key: str, value: str):
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(key + "="):
                    lines.append(f'{key}="{value}"\n')
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f'{key}="{value}"\n')
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ── 管理员状态 ────────────────────────────────────

def is_admin_configured() -> bool:
    """检查管理员是否已配置"""
    env = _load_env_file()
    return ADMIN_ENV_PASSWORD_HASH in env and ADMIN_ENV_PASSWORD_SALT in env


def get_admin_username() -> str:
    """获取管理员用户名"""
    env = _load_env_file()
    return env.get(ADMIN_ENV_USERNAME, "admin")


def verify_admin(username: str, password: str) -> bool:
    """验证管理员身份"""
    env = _load_env_file()
    stored_user = env.get(ADMIN_ENV_USERNAME, "")
    stored_hash = env.get(ADMIN_ENV_PASSWORD_HASH, "")
    stored_salt = env.get(ADMIN_ENV_PASSWORD_SALT, "")

    if not stored_hash or not stored_salt:
        return False
    if username != stored_user:
        return False
    return _verify_password(password, stored_salt, stored_hash)


# ── 令牌管理 ────────────────────────────────────

class TokenManager:
    """简单的内存令牌管理器"""

    def __init__(self):
        self._tokens: Dict[str, float] = {}

    def create_token(self) -> str:
        token = str(uuid.uuid4())
        self._tokens[token] = time.time()
        self._cleanup()
        return token

    def verify_token(self, token: str) -> bool:
        if token not in self._tokens:
            return False
        created_at = self._tokens[token]
        if time.time() - created_at > TOKEN_EXPIRE_SECONDS:
            del self._tokens[token]
            return False
        return True

    def revoke_token(self, token: str):
        self._tokens.pop(token, None)

    def _cleanup(self):
        now = time.time()
        expired = [t for t, ts in self._tokens.items() if now - ts > TOKEN_EXPIRE_SECONDS]
        for t in expired:
            del self._tokens[t]

    @property
    def active_token_count(self) -> int:
        self._cleanup()
        return len(self._tokens)


token_manager = TokenManager()
