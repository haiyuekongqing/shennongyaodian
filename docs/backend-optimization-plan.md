# 后端优化点分析（支撑药典 UI 所需的改造）

> 分析日期：2026-06-17

---

## 一、当前后端的问题清单

### 1. 导入接口是同步阻塞的 — ❌ 关键问题

所有导入接口（`/api/knowledge/import`、`/api/knowledge/upload`、`/api/knowledge/batch-import`、`/api/graph/import`、`/api/graph/upload`）都是**同步执行**的。Uvicorn 只开了 `--workers 1`，大文件导入会：

- 阻塞整个 API 服务（期间其他请求无法处理）
- 导致 HTTP 超时（浏览器/反向代理 30-60s 断开）
- 用户看不到任何进度反馈

**需要改造为异步任务模式。**

### 2. 缺少任务状态查询接口 — ❌ 关键问题

前端需要知道导入任务的状态（进行中/成功/失败/超时），目前没有任何任务追踪机制。

**需要新增：**
- 任务管理系统（追踪异步任务的执行状态）
- `GET /api/tasks/{task_id}` — 查询单个任务状态
- `GET /api/tasks` — 查询任务列表（用于通知中心）

### 3. 缺少静态文件服务 — ❌ 必需

FastAPI 没有挂载静态文件目录，需要新增：
```python
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

### 4. 缺少多文件上传接口 — ⚠️ 需要

当前 `/api/knowledge/upload` 只接收单文件。UI 需要支持一次拖入多个文件。

### 5. 聊天无会话管理 — ⚠️ 可选

`UserSession` 模型是死的（只定义了表，没有读取也没有 API），`MedicalAgent` 里用内存共享的 ConversationBufferMemory，所有用户共用同一个上下文。

### 6. 错误响应格式不统一 — ⚠️ 建议优化

部分端点返回 dict（如 graph 路由），部分返回 MessageResponse，前端处理需要统一格式。

---

## 二、需要新增的后端功能

### 2.1 后台任务系统

位置：`src/task_manager.py`（新建）

```python
class TaskManager:
    """异步任务管理器，追踪导入等耗时操作的状态"""
    
    def create_task(task_type: str, file_name: str) -> str  # 返回 task_id
    def update_task(task_id: str, status, message, details=None)
    def get_task(task_id: str) -> TaskInfo
    def list_tasks(limit=50) -> List[TaskInfo]
    
    # 支持 with 上下文自动更新状态
    def run_import_knowledge(file_paths, chunk_size, overlap)  # 在线程中运行
    def run_import_graph(file_path, mode, entity_types)        # 在线程中运行
```

技术选型：用 `threading.Thread` + 内存 dict（简单可靠，不引入 Redis/Celery），应用重启后任务历史丢失也可以接受（或后续升级到数据库持久化）。

### 2.2 新的 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tasks/import-knowledge` | 异步导入知识（接收文件路径列表） |
| POST | `/api/tasks/import-graph` | 异步导入图谱（接收文件路径） |
| GET | `/api/tasks/{task_id}` | 查询任务状态 |
| GET | `/api/tasks/history` | 查询最近任务列表 |

### 2.3 多文件上传端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/knowledge/upload-multiple` | 多文件上传（返回 task_id） |
| POST | `/api/graph/upload-multiple` | 多图谱文件上传（返回 task_id） |

### 2.4 静态文件服务

```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

路由优先级注意：静态文件挂载需要放在所有 API 路由之后，避免覆盖 API。

---

## 三、无需改动（可直接使用）

### ✅ 问答接口
`POST /api/chat` — 已是 JSON 接口，直接对接前端

### ✅ 知识库状态
`GET /api/knowledge/status`、`GET /api/knowledge/files`、`GET /api/knowledge/statistics`

### ✅ 图谱查询
`POST /api/graph/query`、`POST /api/graph/multi-hop` — 用于 UI 展示

### ✅ CORS
已配置 `allow_origins=["*"]`，前端可以从任何来源访问

---

## 四、前端技术方案

| 项目 | 选择 | 原因 |
|------|------|------|
| 部署方式 | FastAPI 挂载静态文件 | 无需额外容器，零构建步骤 |
| 前端框架 | 纯 HTML + CSS + JS | 避免 Node.js 依赖，匹配项目技术栈 |
| UI 风格 | 传统线装书风格（CSS 3D 变换） | 契合"药典"主题 |
| 数据请求 | Fetch API | 零依赖 |
| Icon 库 | Font Awesome CDN 或 Lucide Icons | 通知图标等 |
| 消息通知 | SSE 轮询 + 本地通知存储 | 定时查 `/api/tasks/history` |

文件结构：
```
static/
├── index.html        # 主页面（书籍 UI）
├── css/
│   └── style.css     # 所有样式
├── js/
│   ├── app.js        # 主逻辑
│   ├── api.js        # API 封装
│   └── notifications.js  # 通知系统
└── assets/           # 图片等静态资源
```

### 前端 UI 布局

```
┌──────────────────────────────────────┐
│  ┌────────┐  ┌───────────────────┐   │
│  │ 书页左  │  │   书页右          │   │
│  │        │  │                   │   │
│  │ [问药] │  │   (内容区域)      │   │
│  │ [收录] │  │   根据选择的       │   │
│  │        │  │   功能切换         │   │
│  │        │  │                   │   │
│  └────────┘  └───────────────────┘   │
│        🔔 (通知图标，固定右上角)     │
└──────────────────────────────────────┘
```

- **问药** → 聊天界面（输入框 + 消息列表 + 发送按钮）
- **收录 → 古籍收录** → 文件选择 + 上传按钮（调用知识库导入接口）
- **收录 → 图谱收录** → 文件选择 + 模式选择（调用图谱导入接口）
- **通知** → 点击展开下拉列表，显示导入任务状态

---

## 五、实现顺序

1. **TaskManager 后台任务系统**（后端核心改造）
2. **异步导入端点 + 多文件上传**（后端 API）
3. **静态文件服务配置**（后端挂载）
4. **前端 HTML/CSS：书籍 UI 框架**（书页布局、导航）
5. **前端 JS：API 对接**（问药、收录功能）
6. **通知系统**（前后端联动）
