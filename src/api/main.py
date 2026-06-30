"""
FastAPI 主应用入口
"""
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request
from typing import List, Dict, Any, Optional
import uvicorn

from src.config.settings import settings
from src.models.base import db_manager
from src.agents.medical_agent import MedicalAgent
from src.retrieval.neo4j_store import neo4j_store
from src.task_manager import task_manager, TaskStatus
from src.auth import (
    verify_admin, is_admin_configured, get_admin_username,
    token_manager, TOKEN_EXPIRE_SECONDS,
)
from src.api.schemas import (
    ChatRequest, ChatResponse, HealthResponse, HealthCheckRequest,
    VectorStatsResponse, MessageResponse,
    FileListResponse, FileStatisticsResponse,
    KnowledgeImportRequest, KnowledgeBatchImportRequest,
    MilvusQueryRequest, MilvusCollectionInfo, MilvusSearchResult,
    TaskImportKnowledgeRequest, TaskImportGraphRequest,
    TaskUploadKnowledgeRequest,
    TaskInfoResponse, TaskListResponse, TaskCreateResponse,
    LoginRequest, LoginResponse, AdminInfoResponse,
)
from src.api.routes import graph, cache  # 图谱路由 + 缓存路由

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局变量
medical_agent: MedicalAgent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("=" * 60)
    logger.info("中草药智能问答 Agent 启动中...")
    logger.info("=" * 60)

    # 初始化数据库
    db_manager.initialize()
    logger.info("✓ 数据库连接已建立")

    # 初始化 Agent
    global medical_agent
    medical_agent = MedicalAgent()
    logger.info("✓ Agent 初始化完成")

    # 初始化 Neo4j 连接
    try:
        neo4j_store.connect()
        logger.info("✓ Neo4j 连接已建立")
    except Exception as e:
        logger.warning(f"⚠ Neo4j 连接失败（图谱功能不可用）: {e}")

    # 获取模型信息
    model_info = medical_agent.get_model_info()
    logger.info(f"✓ LLM 模型: {model_info['model']}")

    # 获取工具信息
    tool_info = medical_agent.get_tool_info()
    logger.info(f"✓ 工具数量: {len(tool_info['tools'])}")

    # 检查管理员配置
    if is_admin_configured():
        logger.info(f"✓ 管理员已就绪: {get_admin_username()}")
    else:
        logger.warning(f"⚠ 管理员账号未配置，请运行: python scripts/setup_admin.py")

    yield

    # 关闭时执行
    logger.info("应用正在关闭...")
    try:
        neo4j_store.close()
    except Exception:
        pass


# 创建 FastAPI 应用


app = FastAPI(
    title="中草药智能问答 API",
    description="基于 RAG 的中草药智能问答系统",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ 请求日志中间件（过滤 /health 刷屏） ============

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录非健康检查的 HTTP 请求"""
    import time
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start

    if request.url.path != "/health":
        logger.info(
            f"{request.method} {request.url.path} "
            f"{response.status_code} ({elapsed:.3f}s)"
        )
    return response


# ============ 健康检查 ============

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(request: HealthCheckRequest = None) -> HealthResponse:
    """
    健康检查

    Args:
        request: 健康检查请求

    Returns:
        健康检查响应
    """
    if request is None:
        request = HealthCheckRequest()

    # 检查 Milvus
    milvus_status = "unknown"
    neo4j_status = "unknown"
    try:
        if medical_agent:
            vector_stats = medical_agent.vector_tool.get_stats()
            milvus_status = "healthy" if vector_stats else "unknown"

            # 检查混合检索状态
            if medical_agent.use_hybrid_retrieval and medical_agent.hybrid_retriever:
                stats = medical_agent.get_retrieval_stats()
                if stats.get("graph_nodes", 0) > 0:
                    neo4j_status = "healthy"
                else:
                    neo4j_status = "empty"
            else:
                neo4j_status = "disabled"
    except Exception as e:
        milvus_status = f"error: {str(e)}"
        neo4j_status = f"error: {str(e)}"

    return HealthResponse(
        status="healthy",
        milvus_status=milvus_status,
        neo4j_status=neo4j_status,
        api_version="1.0.0",
        timestamp=datetime.now().isoformat()
    )


# ============ 问答接口 ============

@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest) -> ChatResponse:
    """
    医疗问答接口

    Args:
        request: 问答请求

    Returns:
        问答响应
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        # 执行问答
        result = medical_agent.query(
            user_input=request.message,
            session_id=request.session_id,
            user_id=request.user_id
        )

        return ChatResponse(**result)

    except Exception as e:
        logger.error(f"✗ 问答接口错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ 知识库接口 ============

@app.get("/api/knowledge/status", response_model=VectorStatsResponse, tags=["Knowledge"])
async def knowledge_status() -> VectorStatsResponse:
    """
    获取知识库状态

    Returns:
        知识库统计信息
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        stats = medical_agent.vector_tool.get_stats()
        return VectorStatsResponse(**stats)
    except Exception as e:
        logger.error(f"✗ 获取知识库状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/knowledge/import", response_model=MessageResponse, tags=["Knowledge"])
async def import_knowledge(request: KnowledgeImportRequest) -> MessageResponse:
    """
    导入单个知识文件

    Args:
        request: 导入请求

    Returns:
        导入结果
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        import os
        file_path = os.path.join(settings.KNOWLEDGE_BASE_DIR, request.file_path)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"文件不存在: {request.file_path}")

        count = medical_agent.vector_tool.import_file(file_path, request.chunk_size, request.overlap)

        if count == 0:
            return MessageResponse(
                success=True,
                message=f"文件未变化，跳过导入: {request.file_path}"
            )

        return MessageResponse(
            success=True,
            message=f"成功导入 {count} 个知识块"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✗ 导入知识失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/knowledge/upload", response_model=MessageResponse, tags=["Knowledge"])
async def upload_knowledge_file(
    file: UploadFile = File(..., description="要导入的知识文件"),
    chunk_size: int = Form(500, description="分块大小"),
    overlap: int = Form(50, description="分块重叠"),
):
    """
    上传文件并导入知识库

    - 支持格式: .md, .txt, .pdf
    - 文件内容会被分块后存入向量数据库
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    import tempfile
    import shutil

    # 保存上传文件到临时位置
    suffix = Path(file.filename).suffix if file.filename else ".tmp"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        count = medical_agent.vector_tool.import_file(tmp_path, chunk_size, overlap)

        if count == 0:
            return MessageResponse(
                success=True,
                message=f"文件内容未变化，跳过导入: {file.filename}"
            )

        return MessageResponse(
            success=True,
            message=f"成功导入 {count} 个知识块（来自 {file.filename}）"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✗ 上传导入知识失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/api/knowledge/batch-import", response_model=MessageResponse, tags=["Knowledge"])
async def batch_import_knowledge(request: KnowledgeBatchImportRequest) -> MessageResponse:
    """
    批量导入知识文件

    Args:
        request: 批量导入请求

    Returns:
        导入结果
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        import os
        import glob

        directory = os.path.join(settings.KNOWLEDGE_BASE_DIR, request.directory)

        if not os.path.exists(directory):
            raise HTTPException(status_code=404, detail=f"目录不存在: {request.directory}")

        # 统计导入结果
        results = {}
        skipped = 0
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(('.md', '.txt', '.pdf')):
                    file_path = os.path.join(root, file)

                    try:
                        count = medical_agent.vector_tool.import_file(file_path, request.chunk_size, request.overlap)
                        if count == 0:
                            skipped += 1
                        results[file] = count
                    except Exception as e:
                        logger.error(f"✗ 导入文件失败 {file}: {e}")
                        results[file] = 0

        total = sum(results.values())
        msg = f"成功导入 {total} 个知识块（共 {len(results)} 个文件"
        if skipped > 0:
            msg += f"，{skipped} 个文件内容未变化已跳过"
        msg += "）"
        return MessageResponse(
            success=True,
            message=msg
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✗ 批量导入知识失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/knowledge/files", response_model=FileListResponse, tags=["Knowledge"])
async def get_knowledge_files(
    file_types: Optional[str] = Query(None, description="文件类型，逗号分隔")
) -> FileListResponse:
    """
    获取知识库文件列表

    Args:
        file_types: 文件类型过滤（逗号分隔，如：pharmacopedia,treatise）

    Returns:
        文件列表
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        types_list = file_types.split(",") if file_types else None
        files = medical_agent.grep_tool.get_file_list(types_list)

        return FileListResponse(
            files=files,
            total_files=len(files)
        )
    except Exception as e:
        logger.error(f"✗ 获取文件列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/knowledge/statistics", response_model=FileStatisticsResponse, tags=["Knowledge"])
async def get_knowledge_statistics() -> FileStatisticsResponse:
    """
    获取知识库统计信息

    Returns:
        统计信息
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        stats = medical_agent.grep_tool.get_file_statistics()

        return FileStatisticsResponse(**stats)
    except Exception as e:
        logger.error(f"✗ 获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ 通用错误处理 ============

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    logger.error(f"✗ 全局异常: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )


# ── 管理员 Token 验证依赖 ────────────────────────

from fastapi import Request as FastAPIRequest, Header

def verify_admin_token(authorization: str = Header(None)):
    """FastAPI 依赖：验证 Bearer Token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization[7:]
    if not token_manager.verify_token(token):
        raise HTTPException(status_code=401, detail="令牌已过期或无效")
    return token


# ============ 管理员认证接口 ============

@app.post("/api/admin/login", response_model=LoginResponse, tags=["Admin"])
async def admin_login(request: LoginRequest) -> LoginResponse:
    """
    管理员登录

    验证用户名密码，返回认证令牌。
    令牌有效期为 24 小时，用于访问管理端功能。
    """
    if verify_admin(request.username, request.password):
        token = token_manager.create_token()
        return LoginResponse(
            success=True,
            token=token,
            message=f"欢迎, {request.username}",
        )
    # 延迟 1 秒防止暴力破解
    import time
    time.sleep(1)
    return LoginResponse(
        success=False,
        message="用户名或密码错误",
    )


@app.post("/api/admin/logout", tags=["Admin"])
async def admin_logout(token: str = Depends(verify_admin_token)):
    """管理员登出"""
    token_manager.revoke_token(token)
    return {"success": True, "message": "已登出"}


@app.get("/api/admin/info", response_model=AdminInfoResponse, tags=["Admin"])
async def admin_info(token: str = Depends(verify_admin_token)):
    """
    获取管理员信息
    """
    return AdminInfoResponse(
        username="admin",
        token_expire_hours=TOKEN_EXPIRE_SECONDS // 3600,
        active_tokens=token_manager.active_token_count,
    )


if __name__ == "__main__":
    # 启动应用（关闭 uvicorn 自带 access log，使用自定义中间件）
    uvicorn.run(
        "src.api.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.LOG_LEVEL == "DEBUG",
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False
    )


# ============ Milvus 管理接口 ============

@app.get("/api/milvus/collections", response_model=MilvusCollectionInfo, tags=["Milvus"])
async def get_collections() -> MilvusCollectionInfo:
    """
    获取 Milvus 集合信息

    Returns:
        集合信息
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        stats = medical_agent.vector_tool.get_stats()
        return MilvusCollectionInfo(
            name="tcm_knowledge_base",
            description="中草药知识库",
            num_entities=stats.get('num_entities', 0),
            dimension=1024,
            index_type="IVF_FLAT",
            metric_type="IP",
            status="active"
        )
    except Exception as e:
        logger.error(f"✗ 获取集合信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/milvus/query", response_model=List[MilvusSearchResult], tags=["Milvus"])
async def query_milvus(request: MilvusQueryRequest = None) -> List[MilvusSearchResult]:
    """
    查询 Milvus 向量数据

    Args:
        request: 查询请求

    Returns:
        查询结果列表
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        if request is None:
            request = MilvusQueryRequest()

        # 执行向量搜索
        results = medical_agent.vector_tool.search(
            query="测试查询",  # Milvus 查询需要查询文本
            top_k=request.limit,
            filter_condition=None
        )

        # 转换为响应格式
        formatted_results = []
        for i, result in enumerate(results):
            formatted_results.append(
                MilvusSearchResult(
                    id=str(result.get('id', str(i))),
                    score=result.get('distance', 0.0),
                    entity=result.get('entity', {})
                )
            )

        return formatted_results

    except Exception as e:
        logger.error(f"✗ Milvus 查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ 图谱管理接口 ============

app.include_router(graph.router)  # 注册图谱路由

# ============ 缓存管理接口 ============

app.include_router(cache.router)  # 注册缓存路由


# ============ 异步任务接口 ============

@app.post("/api/tasks/import-knowledge", response_model=TaskCreateResponse, tags=["Tasks"])
async def task_import_knowledge(request: TaskImportKnowledgeRequest, token: str = Depends(verify_admin_token)) -> TaskCreateResponse:
    """
    异步导入知识库文件

    接收文件路径列表，后台逐个导入，通过 task_id 查询进度。
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    task_id = task_manager.create_task(
        task_type="knowledge_import",
        file_names=[p.split("/")[-1].split("\\")[-1] for p in request.file_paths],
    )

    # 拼接完整路径
    import os
    full_paths = [
        os.path.join(settings.KNOWLEDGE_BASE_DIR, fp)
        for fp in request.file_paths
    ]

    # 在后台线程执行
    task_manager.run_in_background(
        task_id,
        target=task_manager.import_knowledge,
        kwargs={
            "task_id": task_id,
            "file_paths": full_paths,
            "chunk_size": request.chunk_size,
            "overlap": request.overlap,
        },
        timeout=600,
    )

    task = task_manager.get_task(task_id)
    return TaskCreateResponse(data=TaskInfoResponse(**task.to_dict()))


@app.post("/api/tasks/upload-knowledge", response_model=TaskCreateResponse, tags=["Tasks"])
async def task_upload_knowledge(
    files: List[UploadFile] = File(..., description="知识文件列表"),
    chunk_size: int = Form(500, description="分块大小"),
    overlap: int = Form(50, description="分块重叠"),
    token: str = Depends(verify_admin_token),
):
    """
    上传多个文件并异步导入知识库

    文件保存到临时目录后启动后台导入，立即返回 task_id。
    """
    if not medical_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    import tempfile
    import shutil
    import os

    file_names = [f.filename or f"file_{i}" for i, f in enumerate(files)]
    task_id = task_manager.create_task(
        task_type="knowledge_upload",
        file_names=file_names,
    )

    # 保存文件到临时目录
    tmp_dir = tempfile.mkdtemp(prefix="knowledge_upload_")
    saved_paths = []
    try:
        for file in files:
            if file.filename:
                tmp_path = os.path.join(tmp_dir, file.filename)
                with open(tmp_path, "wb") as f:
                    shutil.copyfileobj(file.file, f)
                saved_paths.append(tmp_path)

        # 后台导入
        task_manager.run_in_background(
            task_id,
            target=task_manager.import_knowledge,
            kwargs={
                "task_id": task_id,
                "file_paths": saved_paths,
                "chunk_size": chunk_size,
                "overlap": overlap,
            },
            timeout=600,
        )
    except Exception as e:
        task_manager.update_task(task_id, "failed", f"文件保存失败: {e}")

    task = task_manager.get_task(task_id)
    return TaskCreateResponse(data=TaskInfoResponse(**task.to_dict()))


@app.post("/api/tasks/import-graph", response_model=TaskCreateResponse, tags=["Tasks"])
async def task_import_graph(request: TaskImportGraphRequest, token: str = Depends(verify_admin_token)) -> TaskCreateResponse:
    """
    异步导入图谱数据

    接收文件路径，后台导入图谱，通过 task_id 查询进度。
    """
    import os

    file_name = request.file_path.split("/")[-1].split("\\")[-1]
    task_id = task_manager.create_task(
        task_type="graph_import",
        file_names=[file_name],
    )

    full_path = os.path.join(settings.KNOWLEDGE_BASE_DIR, request.file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {request.file_path}")

    task_manager.run_in_background(
        task_id,
        target=task_manager.import_graph,
        kwargs={
            "task_id": task_id,
            "file_path": full_path,
            "mode": request.mode,
            "entity_types": request.entity_types,
        },
        timeout=600,
    )

    task = task_manager.get_task(task_id)
    return TaskCreateResponse(data=TaskInfoResponse(**task.to_dict()))


@app.post("/api/tasks/upload-graph", response_model=TaskCreateResponse, tags=["Tasks"])
async def task_upload_graph(
    file: UploadFile = File(..., description="图谱 JSON 文件"),
    mode: str = Form("full_import", description="导入模式：full_import / append"),
    entity_types: Optional[str] = Form(None, description="实体类型过滤（逗号分隔）"),
    token: str = Depends(verify_admin_token),
):
    """
    上传图谱 JSON 文件并异步导入

    返回 task_id，前端轮询任务状态。
    """
    import tempfile
    import shutil
    import os

    file_name = file.filename or "graph.json"
    task_id = task_manager.create_task(
        task_type="graph_upload",
        file_names=[file_name],
    )

    suffix = Path(file.filename).suffix if file.filename else ".json"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    entity_list = entity_types.split(",") if entity_types else None

    task_manager.run_in_background(
        task_id,
        target=task_manager.import_graph,
        kwargs={
            "task_id": task_id,
            "file_path": tmp_path,
            "mode": mode,
            "entity_types": entity_list,
        },
        timeout=600,
    )

    task = task_manager.get_task(task_id)
    return TaskCreateResponse(data=TaskInfoResponse(**task.to_dict()))


@app.get("/api/tasks/{task_id}", response_model=TaskCreateResponse, tags=["Tasks"])
async def get_task(task_id: str) -> TaskCreateResponse:
    """
    查询单个任务的状态和结果
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return TaskCreateResponse(data=TaskInfoResponse(**task.to_dict()))


@app.get("/api/tasks", response_model=TaskListResponse, tags=["Tasks"])
async def list_tasks(limit: int = Query(50, description="返回条数", ge=1, le=200)) -> TaskListResponse:
    """
    获取任务历史列表（按创建时间倒序）
    用于通知中心展示导入结果
    """
    tasks = task_manager.list_tasks(limit=limit)
    return TaskListResponse(
        data=[TaskInfoResponse(**t) for t in tasks],
        total=len(tasks),
    )


# ============ 静态文件服务（药典 Web UI） ============

from fastapi.staticfiles import StaticFiles
import os as _os

_static_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), "static")
if _os.path.exists(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
    logger.info(f"✓ 静态文件服务已挂载: {_static_dir}")
