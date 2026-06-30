"""
图谱管理 API 路由
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json
import logging
import os

from src.retrieval.neo4j_store import neo4j_store
from src.graph_importer import MedicalGraphImporter
from src.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["知识图谱"])


# ==================== 请求模型 ====================

class GraphStatsResponse(BaseModel):
    """图谱统计响应"""
    total_nodes: int
    total_relationships: int
    node_types: List[Dict[str, Any]]
    relationship_types: List[Dict[str, Any]]


class GraphImportRequest(BaseModel):
    """图谱导入请求"""
    file: str = Field(..., description="JSON文件路径")
    entity_types: Optional[List[str]] = Field(None, description="实体类型列表")
    mode: str = Field("full_import", description="导入模式: full_import/append")


class GraphQueryRequest(BaseModel):
    """图谱查询请求"""
    entity_type: str = Field(..., description="实体类型")
    name: str = Field(..., description="实体名称")
    fields: Optional[List[str]] = Field(None, description="返回的字段列表")


class MultiHopQueryRequest(BaseModel):
    """多跳查询请求"""
    start_entity: str = Field(..., description="起始实体名称")
    start_type: Optional[str] = Field(None, description="起始实体类型")
    hop_count: int = Field(3, description="跳数")
    path_types: Optional[List[str]] = Field(None, description="关系类型列表")


# ==================== API 端点 ====================

@router.get("/stats", response_model=GraphStatsResponse, summary="获取图谱统计信息")
async def get_graph_stats():
    """
    获取知识图谱统计信息

    - **total_nodes**: 图谱中节点总数
    - **total_relationships**: 图谱中关系总数
    - **node_types**: 节点类型分布
    - **relationship_types**: 关系类型分布
    """
    try:
        stats = neo4j_store.get_stats()
        return GraphStatsResponse(**stats)
    except Exception as e:
        logger.error(f"获取图谱统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import", summary="导入图谱数据")
async def import_graph_data(request: GraphImportRequest):
    """
    从 JSON 文件导入图谱数据到 Neo4j

    - **file**: JSON 文件路径（相对于 knowledge_base 目录）
    - **entity_types**: 限制处理的实体类型（可选）
    - **mode**: 导入模式（full_import: 清空后导入, append: 追加导入）
    """
    try:
        logger.info(f"开始导入图谱: {request.file}, 模式: {request.mode}")

        # 构建完整的文件路径
        full_file_path = os.path.join(settings.KNOWLEDGE_BASE_DIR, request.file)
        logger.info(f"完整文件路径: {full_file_path}")

        # 创建导入器
        importer = MedicalGraphImporter(neo4j_store)

        # 执行导入
        stats = importer.import_medical_json(
            file_path=full_file_path,
            entity_types=request.entity_types,
            mode=request.mode
        )

        return {
            "success": True,
            "message": "导入成功",
            "statistics": stats,
            "file": request.file,
            "full_path": full_file_path
        }

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件不存在: {full_file_path}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail=f"JSON 文件格式错误: {request.file}")
    except Exception as e:
        logger.error(f"导入图谱失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", summary="上传文件并导入图谱")
async def upload_graph_data(
    file: UploadFile = File(..., description="JSON 图谱数据文件"),
    entity_types: Optional[str] = Form(None, description="实体类型列表（逗号分隔）"),
    mode: str = Form("full_import", description="导入模式: full_import/append"),
):
    """
    上传 JSON 文件并导入图谱数据到 Neo4j

    - 支持 JSON 数组格式 和 JSON Lines (NDJSON) 格式
    - **entity_types**: 限制处理的实体类型（逗号分隔，可选）
    - **mode**: 导入模式（full_import: 清空后导入, append: 追加导入）
    """
    if not file.filename or not file.filename.endswith(('.json', '.jsonl')):
        raise HTTPException(status_code=400, detail="仅支持 .json / .jsonl 文件")

    import tempfile
    import shutil

    # 保存上传文件到临时位置
    suffix = ".json"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        logger.info(f"开始上传导入图谱: {file.filename}, 模式: {mode}")

        # 解析 entity_types
        types_list = entity_types.split(",") if entity_types else None

        # 创建导入器
        importer = MedicalGraphImporter(neo4j_store)

        # 执行导入
        stats = importer.import_medical_json(
            file_path=tmp_path,
            entity_types=types_list,
            mode=mode
        )

        return {
            "success": True,
            "message": "导入成功",
            "statistics": stats,
            "filename": file.filename,
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail=f"JSON 文件格式错误: {file.filename}")
    except Exception as e:
        logger.error(f"上传导入图谱失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/query", summary="图谱查询")
async def query_graph(request: GraphQueryRequest):
    """
    根据实体类型和名称查询图谱

    - **entity_type**: 实体类型（Drug, Disease, Formula, Symptom等）
    - **name**: 实体名称
    - **fields**: 返回的字段列表（可选）
    """
    try:
        results = neo4j_store.query_by_name(
            entity_type=request.entity_type,
            name=request.name
        )
        return {
            "success": True,
            "results": results
        }
    except Exception as e:
        logger.error(f"图谱查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multi-hop", summary="多跳查询")
async def multi_hop_query(request: MultiHopQueryRequest):
    """
    多跳查询（例如：症状 → 疾病 → 用药）

    - **start_entity**: 起始实体名称
    - **start_type**: 起始实体类型（可选）
    - **hop_count**: 跳数（默认3）
    - **path_types**: 关系类型列表（可选）
    """
    try:
        results = neo4j_store.multi_hop_query(
            start_entity=request.start_entity,
            start_type=request.start_type,
            hop_count=request.hop_count,
            path_types=request.path_types
        )
        return {
            "success": True,
            "results": results,
            "hop_count": request.hop_count
        }
    except Exception as e:
        logger.error(f"多跳查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear", summary="清空图谱数据")
async def clear_graph():
    """
    清空所有图谱数据（⚠️ 危险操作）

    此操作不可恢复，请谨慎使用。
    """
    try:
        neo4j_store.clear_all()
        return {
            "success": True,
            "message": "图谱数据已清空"
        }
    except Exception as e:
        logger.error(f"清空图谱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export", summary="导出图谱数据")
async def export_graph(limit: int = 100):
    """
    导出图谱数据为 JSON

    - **limit**: 导出数量限制（默认100）
    """
    try:
        data = neo4j_store.export_graph(limit=limit)
        return {
            "success": True,
            "count": len(data),
            "data": data
        }
    except Exception as e:
        logger.error(f"导出图谱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
