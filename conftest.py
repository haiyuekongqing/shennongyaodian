"""
pytest 配置文件
"""
import pytest
import os
import sys

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def api_client():
    """创建 API 客户端"""
    import httpx
    # 注意：实际测试需要启动 API 服务
    # 这里仅创建客户端实例
    # client = httpx.AsyncClient(app=app, base_url="http://localhost:8000")
    # yield client
    # await client.aclose()
    pass
