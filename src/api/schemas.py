"""
API 数据模型 (Pydantic Schemas)
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ============ 请求模型 ============

class ChatRequest(BaseModel):
    """问答请求"""
    message: str = Field(..., description="用户消息", min_length=1, max_length=2000)
    session_id: Optional[str] = Field(None, description="会话 ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    top_k: Optional[int] = Field(5, description="检索返回结果数量", ge=1, le=20)


class KnowledgeImportRequest(BaseModel):
    """知识库导入请求"""
    file_path: str = Field(..., description="文件路径", max_length=500)
    chunk_size: Optional[int] = Field(500, description="分块大小", ge=100, le=2000)
    overlap: Optional[int] = Field(50, description="分块重叠", ge=0, le=500)


class KnowledgeBatchImportRequest(BaseModel):
    """知识库批量导入请求"""
    directory: str = Field(..., description="目录路径", max_length=500)
    chunk_size: Optional[int] = Field(500, description="分块大小", ge=100, le=2000)
    overlap: Optional[int] = Field(50, description="分块重叠", ge=0, le=500)


class HealthCheckRequest(BaseModel):
    """健康检查请求"""
    check_milvus: Optional[bool] = Field(True, description="检查 Milvus 状态")


# ============ 响应模型 ============

class ChatResponse(BaseModel):
    """问答响应"""
    success: bool = Field(..., description="请求是否成功")
    answer: str = Field(..., description="生成的回答")
    disclaimer: str = Field(..., description="医疗免责声明")
    intent: Optional[str] = Field(None, description="意图类型")
    confidence: Optional[float] = Field(None, description="意图置信度")
    suggested_tool: Optional[str] = Field(None, description="建议的工具")
    retrieval_type: Optional[str] = Field(None, description="检索类型")
    graph_results: Optional[int] = Field(None, description="图谱检索结果数")
    vector_results: Optional[int] = Field(None, description="向量检索结果数")
    timing: Optional[List[Dict[str, Any]]] = Field(None, description="调用链时序")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="服务状态")
    milvus_status: str = Field(..., description="Milvus 状态")
    neo4j_status: str = Field(..., description="Neo4j 图谱状态")
    api_version: str = Field(..., description="API 版本")
    timestamp: str = Field(..., description="检查时间戳")


class VectorStatsResponse(BaseModel):
    """向量统计响应"""
    collection_name: str = Field(..., description="集合名称")
    num_entities: int = Field(..., description="向量数量")
    total_chunks: int = Field(..., description="总分块数")
    embedding_model: str = Field(..., description="Embedding 模型")


class FileListResponse(BaseModel):
    """文件列表响应"""
    files: List[Dict[str, Any]] = Field(..., description="文件列表")
    total_files: int = Field(..., description="文件总数")


class FileStatisticsResponse(BaseModel):
    """文件统计响应"""
    total_files: int = Field(..., description="文件总数")
    total_size: int = Field(..., description="总大小（字节）")
    by_type: Dict[str, int] = Field(..., description="按类型统计")


class MessageResponse(BaseModel):
    """通用消息响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="消息内容")


# ============ API 响应包装 ============

class APIResponse(BaseModel):
    """API 响应包装"""
    success: bool = Field(..., description="请求是否成功")
    data: Any = Field(None, description="返回数据")
    message: Optional[str] = Field(None, description="消息")
    error: Optional[str] = Field(None, description="错误信息")


# ============ 错误响应 ============

class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = Field(False, description="请求失败")
    error: str = Field(..., description="错误信息")
    timestamp: str = Field(..., description="错误时间戳")


# ============ Milvus 管理模型 ============

class MilvusQueryRequest(BaseModel):
    """Milvus 查询请求"""
    collection_name: str = Field("tcm_knowledge_base", description="集合名称")
    limit: int = Field(10, ge=1, le=100, description="返回结果数量")
    offset: int = Field(0, ge=0, description="偏移量")


class MilvusCollectionInfo(BaseModel):
    """Milvus 集合信息"""
    name: str
    description: str
    num_entities: int
    dimension: int
    index_type: str
    metric_type: str
    status: str


class MilvusSearchResult(BaseModel):
    """Milvus 搜索结果"""
    id: str
    score: float
    entity: Dict[str, Any]


# ============ 任务管理模型 ============

class TaskImportKnowledgeRequest(BaseModel):
    """异步导入知识库请求"""
    file_paths: List[str] = Field(..., description="文件路径列表", min_length=1, max_length=100)
    chunk_size: Optional[int] = Field(500, description="分块大小", ge=100, le=2000)
    overlap: Optional[int] = Field(50, description="分块重叠", ge=0, le=500)


class TaskUploadKnowledgeRequest(BaseModel):
    """异步上传知识库请求（多文件）"""
    chunk_size: Optional[int] = Field(500, description="分块大小", ge=100, le=2000)
    overlap: Optional[int] = Field(50, description="分块重叠", ge=0, le=500)


class TaskImportGraphRequest(BaseModel):
    """异步导入图谱请求"""
    file_path: str = Field(..., description="JSON 文件路径", max_length=500)
    mode: Optional[str] = Field("full_import", description="导入模式：full_import / append")
    entity_types: Optional[List[str]] = Field(None, description="实体类型过滤")


class TaskInfoResponse(BaseModel):
    """任务信息响应"""
    task_id: str
    task_type: str
    file_names: List[str]
    status: str
    message: str
    details: Dict[str, Any]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskListResponse(BaseModel):
    """任务列表响应"""
    success: bool = True
    data: List[TaskInfoResponse]
    total: int


class TaskCreateResponse(BaseModel):
    """创建任务响应"""
    success: bool = True
    data: TaskInfoResponse


# ============ 管理员认证模型 ============

class LoginRequest(BaseModel):
    """管理员登录请求"""
    username: str = Field(..., description="管理员用户名", min_length=1, max_length=50)
    password: str = Field(..., description="密码", min_length=1, max_length=100)


class LoginResponse(BaseModel):
    """管理员登录响应"""
    success: bool = True
    token: str = Field("", description="认证令牌")
    message: str = ""


class AdminInfoResponse(BaseModel):
    """管理员信息响应"""
    username: str
    token_expire_hours: int = 24
    active_tokens: int = 0
