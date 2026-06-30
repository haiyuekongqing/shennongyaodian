"""
缓存管理 API 路由
"""
from fastapi import APIRouter
from typing import Dict, Any
import logging

from src.agents.tools.cache_tool import CacheTool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cache", tags=["缓存管理"])

# 全局缓存工具实例
cache_tool = CacheTool()


@router.get("/status", summary="获取缓存状态")
async def get_cache_status() -> Dict[str, Any]:
    """获取所有缓存的状态统计"""
    stats = cache_tool.get_all_cache_stats()
    return {
        "success": True,
        **stats
    }


@router.post("/clear", summary="清空所有缓存")
async def clear_cache() -> Dict[str, Any]:
    """清空 LLM 缓存 + 语义缓存 + Embedding 缓存"""
    ok = cache_tool.clear_all_cache()
    return {
        "success": ok,
        "message": "所有缓存已清空" if ok else "清空缓存失败"
    }


@router.post("/clear/semantic", summary="清空语义缓存")
async def clear_semantic_cache() -> Dict[str, Any]:
    """仅清空语义缓存"""
    ok = cache_tool.clear_semantic_cache()
    return {
        "success": ok,
        "message": "语义缓存已清空" if ok else "清空语义缓存失败"
    }


@router.post("/clear/llm", summary="清空 LLM 缓存")
async def clear_llm_cache() -> Dict[str, Any]:
    """仅清空 LLM 缓存"""
    ok = cache_tool.clear_llm_cache()
    return {
        "success": ok,
        "message": "LLM 缓存已清空" if ok else "清空 LLM 缓存失败"
    }


@router.post("/clear/embedding", summary="清空 Embedding 缓存")
async def clear_embedding_cache() -> Dict[str, Any]:
    """仅清空 Embedding 缓存"""
    ok = cache_tool.clear_embedding_cache()
    return {
        "success": ok,
        "message": "Embedding 缓存已清空" if ok else "清空 Embedding 缓存失败"
    }
