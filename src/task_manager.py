"""
异步任务管理器
支持后台导入任务的状态追踪（知识库 + 图谱）
"""
import uuid
import time
import logging
import threading
from enum import Enum
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TaskType(str, Enum):
    KNOWLEDGE_IMPORT = "knowledge_import"
    KNOWLEDGE_UPLOAD = "knowledge_upload"
    GRAPH_IMPORT = "graph_import"
    GRAPH_UPLOAD = "graph_upload"


class TaskInfo:
    """任务信息"""

    def __init__(
        self,
        task_id: str,
        task_type: TaskType,
        file_names: List[str],
        status: TaskStatus = TaskStatus.PENDING,
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.file_names = file_names
        self.status = status
        self.message = ""
        self.details: Dict[str, Any] = {}
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "file_names": self.file_names,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class TaskManager:
    """异步任务管理器（单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._tasks: Dict[str, TaskInfo] = {}
            self._tasks_lock = threading.Lock()
            self._max_history = 200  # 最多保留 200 条历史
            self._initialized = True

    # ── 任务 CRUD ──────────────────────────────────────────

    def create_task(
        self,
        task_type: TaskType,
        file_names: List[str],
    ) -> str:
        """创建任务，返回 task_id"""
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            file_names=file_names,
        )
        with self._tasks_lock:
            self._tasks[task_id] = task
            # 超出上限时清理最旧的任务
            if len(self._tasks) > self._max_history:
                sorted_keys = sorted(self._tasks.keys(), key=lambda k: self._tasks[k].created_at)
                for old_key in sorted_keys[:len(self._tasks) - self._max_history]:
                    del self._tasks[old_key]
        return task_id

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """查询单个任务"""
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取任务历史（按创建时间倒序）"""
        with self._tasks_lock:
            tasks = list(self._tasks.values())
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return [t.to_dict() for t in tasks[:limit]]

    def update_task(
        self,
        task_id: str,
        status: TaskStatus,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
    ):
        """更新任务状态"""
        task = self.get_task(task_id)
        if not task:
            logger.warning(f"任务 {task_id} 不存在")
            return
        task.status = status
        task.message = message
        if details:
            task.details.update(details)
        if status == TaskStatus.RUNNING and task.started_at is None:
            task.started_at = datetime.now()
        if status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT):
            task.completed_at = datetime.now()
        logger.info(f"任务 {task_id} 状态更新: {status} - {message}")

    # ── 后台执行 ──────────────────────────────────────────

    def run_in_background(
        self,
        task_id: str,
        target: Callable,
        args: tuple = (),
        kwargs: dict = None,
        timeout: int = 600,  # 默认 10 分钟超时
    ):
        """在后台线程中执行任务"""
        if kwargs is None:
            kwargs = {}

        def _wrapper():
            self.update_task(task_id, TaskStatus.RUNNING, "任务执行中...")
            try:
                # 带超时执行
                thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
                thread.start()
                thread.join(timeout=timeout)

                if thread.is_alive():
                    # 超时了，线程仍在运行
                    self.update_task(task_id, TaskStatus.TIMEOUT, f"任务执行超时（{timeout}秒）")
                    logger.warning(f"任务 {task_id} 超时（{timeout}s），线程仍在运行")
                else:
                    # 线程正常结束，target 内部应已更新状态
                    # 如果 target 内部没有更新状态，这里兜底
                    task = self.get_task(task_id)
                    if task and task.status == TaskStatus.RUNNING:
                        self.update_task(task_id, TaskStatus.SUCCESS, "任务完成")
            except Exception as e:
                self.update_task(task_id, TaskStatus.FAILED, str(e))
                logger.error(f"任务 {task_id} 失败: {e}")

        thread = threading.Thread(target=_wrapper, daemon=True, name=f"task-{task_id}")
        thread.start()
        return task_id

    # ── 导入任务（知识库） ────────────────────────────────

    def import_knowledge(
        self,
        task_id: str,
        file_paths: List[str],
        chunk_size: int = 500,
        overlap: int = 50,
    ):
        """
        后台导入知识库文件（在后台线程中调用）
        逐个文件导入，更新进度
        """
        from src.retrieval.vector_store import VectorStore

        vector_store = VectorStore()
        vector_store.initialize()

        total_chunks = 0
        succeeded = 0
        failed = 0
        errors = []

        for i, file_path in enumerate(file_paths):
            self.update_task(
                task_id,
                TaskStatus.RUNNING,
                f"正在导入 ({i + 1}/{len(file_paths)}): {file_path}",
                details={"progress": i, "total": len(file_paths), "current_file": file_path},
            )
            try:
                count = vector_store.import_file(file_path, chunk_size, overlap)
                if count > 0:
                    total_chunks += count
                    succeeded += 1
                else:
                    succeeded += 1  # 已存在（哈希匹配）也算成功
            except Exception as e:
                failed += 1
                errors.append(f"{file_path}: {e}")
                logger.error(f"✗ 导入知识文件失败 {file_path}: {e}")

        msg = f"导入完成：{succeeded} 个成功"
        if failed > 0:
            msg += f"，{failed} 个失败"
        msg += f"，共 {total_chunks} 个知识块"

        self.update_task(
            task_id,
            TaskStatus.SUCCESS,
            msg,
            details={
                "total_chunks": total_chunks,
                "succeeded": succeeded,
                "failed": failed,
                "errors": errors,
                "file_paths": file_paths,
            },
        )

    # ── 导入任务（图谱） ────────────────────────────────

    def import_graph(
        self,
        task_id: str,
        file_path: str,
        mode: str = "full_import",
        entity_types: Optional[List[str]] = None,
    ):
        """
        后台导入图谱数据（在后台线程中调用）
        """
        from src.graph_importer import MedicalGraphImporter

        self.update_task(
            task_id,
            TaskStatus.RUNNING,
            f"正在导入图谱: {file_path} (mode={mode})",
        )

        try:
            importer = MedicalGraphImporter()
            result = importer.import_medical_json(file_path, entity_types=entity_types, mode=mode)

            msg = f"图谱导入完成"
            if isinstance(result, dict):
                msg = f"图谱导入完成：{result.get('nodes', 0)} 个节点, {result.get('relationships', 0)} 条关系"

            self.update_task(
                task_id,
                TaskStatus.SUCCESS,
                msg,
                details={"result": result if isinstance(result, dict) else str(result)},
            )
        except Exception as e:
            self.update_task(task_id, TaskStatus.FAILED, f"图谱导入失败: {e}")
            logger.error(f"✗ 导入图谱失败: {e}")


# 全局单例
task_manager = TaskManager()
