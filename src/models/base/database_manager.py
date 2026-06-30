"""
数据库连接管理器
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
import os

from src.config.settings import settings


class DatabaseManager:
    """数据库管理器单例"""

    _instance = None
    _engine = None
    _SessionLocal = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def initialize(self):
        """初始化数据库连接"""
        if self._engine is not None:
            return

        # 创建数据库连接
        self._engine = create_engine(
            settings.DATABASE_URL,
            poolclass=StaticPool,
            echo=settings.LOG_LEVEL == 'DEBUG',
            connect_args={"check_same_thread": False} if 'sqlite' in settings.DATABASE_URL else {}
        )

        # 创建 Session 工厂
        self._SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self._engine)

        # 创建表
        from src.models.base.database import Base
        Base.metadata.create_all(bind=self._engine)

        print("[OK] Database connection established, tables created")

    @contextmanager
    def get_session(self) -> Session:
        """
        获取数据库会话（上下文管理器）
        自动初始化数据库连接（如尚未初始化）

        使用示例:
        with db_manager.get_session() as session:
            # 执行数据库操作
            pass
        """
        if self._SessionLocal is None:
            self.initialize()
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_engine(self):
        """获取 SQLAlchemy Engine"""
        if self._engine is None:
            self.initialize()
        return self._engine

    def drop_all_tables(self):
        """删除所有表（仅用于测试）"""
        from src.models.base.database import Base
        Base.metadata.drop_all(bind=self._engine)
        print("[OK] All tables deleted")


# 创建全局数据库管理器实例
db_manager = DatabaseManager()
