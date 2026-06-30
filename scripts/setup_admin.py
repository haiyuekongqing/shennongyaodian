#!/usr/bin/env python3
"""
管理员账号设置工具

用法：
  python scripts/setup_admin.py                    # 交互式设置
  python scripts/setup_admin.py --username admin --password 你的密码  # 非交互式
"""
import os
import sys
import hashlib
import secrets
import getpass

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".env")


def load_env() -> dict:
    """读取 .env 文件"""
    result = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    result[key.strip()] = value.strip().strip("\"'")
    return result


def save_env(key: str, value: str):
    """保存变量到 .env"""
    lines = []
    found = False
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(key + "="):
                    lines.append(f'{key}="{value}"\n')
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f'{key}="{value}"\n')
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def remove_env(key: str):
    """删除 .env 中的变量"""
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        for line in lines:
            if not line.startswith(key + "="):
                f.write(line)


def set_admin_password(username: str, password: str):
    """设置管理员账号密码（加密存储）"""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    # 清除旧的认证相关变量
    remove_env("ADMIN_PASSWORD")
    remove_env("ADMIN_USERNAME")
    remove_env("ADMIN_PASSWORD_SALT")
    remove_env("ADMIN_PASSWORD_HASH")

    # 写入新的加密凭据
    save_env("ADMIN_USERNAME", username)
    save_env("ADMIN_PASSWORD_SALT", salt)
    save_env("ADMIN_PASSWORD_HASH", pwd_hash)

    print(f"✅ 管理员账号已设置: {username}")
    print(f"   密码已加密存储（SHA-256 + 随机盐），安全存留在 .env 中")
    print(f"   登录地址: http://localhost:8000 → 左下角「管理员登录」")
    print(f"   如需修改密码，重新运行本脚本即可")


def main():
    # 解析命令行参数
    username = None
    password = None

    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--username" and i + 2 < len(sys.argv):
            username = sys.argv[i + 2]
        elif arg == "--password" and i + 2 < len(sys.argv):
            password = sys.argv[i + 2]

    if username and password:
        set_admin_password(username, password)
        return

    # 交互式模式
    print("=" * 50)
    print("  神农本草 — 管理员账号设置")
    print("=" * 50)
    print()

    env = load_env()
    existing_user = env.get("ADMIN_USERNAME", "")
    if existing_user:
        print(f"当前管理员: {existing_user}")
        confirm = input("是否修改密码？(y/n): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return
        print()

    while not username:
        username = input("管理员用户名 (默认 admin): ").strip() or "admin"

    while not password:
        p1 = getpass.getpass("密码: ")
        p2 = getpass.getpass("确认密码: ")
        if p1 != p2:
            print("❌ 两次密码不一致，请重新输入")
            continue
        if len(p1) < 4:
            print("❌ 密码至少 4 位")
            continue
        password = p1

    print()
    set_admin_password(username, password)


if __name__ == "__main__":
    main()
