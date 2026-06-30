"""
配置管理模块
从环境变量加载配置
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """应用配置"""

    # 数据库配置
    DATABASE_URL: str = "sqlite:///./data/tcm.db"

    # Neo4j 配置
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j"

    # Milvus 配置
    MILVUS_HOST: str = "milvus"
    MILVUS_PORT: int = 19530

    # LLM 配置
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "GLM-4.7-Flash"
    OPENAI_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"

    # Embedding 模型配置
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DEVICE: str = "cpu"  # cpu 或 cuda

    # 知识库配置
    KNOWLEDGE_BASE_DIR: str = "data/knowledge_base"

    # 应用配置
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.log"

    # 安全配置
    API_KEY: Optional[str] = None

    # 管理员认证配置（由 auth 模块管理，仅声明避免 Pydantic 报错）
    ADMIN_USERNAME: Optional[str] = None
    ADMIN_PASSWORD_SALT: Optional[str] = None
    ADMIN_PASSWORD_HASH: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None  # 仅用于 scripts/setup_admin.py

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
