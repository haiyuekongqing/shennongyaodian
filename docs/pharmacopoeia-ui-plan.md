# 药典 UI + 后端异步导入改造计划

## Context

当前项目只有纯 JSON API 后端，用户无法直观使用。需要：
1. 创建一个"药典"书籍风格的 Web UI，包含问药（聊天）、收录（知识导入）两大功能
2. 导入接口改为异步（当前同步阻塞会卡死整个 API）
3. 增加通知系统展示导入结果

后端当前有 **6 个需要改造的点**（详见 `docs/backend-optimization-plan.md`），核心是异步任务系统和静态文件服务。

---

## 一、后端改造

### 1.1 后台任务系统 — `src/task_manager.py`（新建）

```python
class TaskManager:
    _tasks: Dict[str, dict]  # 内存存储，key=task_id
    _lock: threading.Lock
    
    def create_task(type, file_name) -> str           # 创建任务，返回 task_id
    def update_task(task_id, status, message)         # 更新状态
    def get_task(task_id) -> dict                     # 查询
    def list_tasks(limit=50) -> list                  # 历史列表
    def run_in_background(func, *args, **kwargs)      # 线程中执行
    
    # 导入方法（在后台线程运行）
    def import_knowledge(task_id, file_paths, chunk_size, overlap)
    def import_graph(task_id, file_path, mode, entity_types)

task_manager = TaskManager()  # 全局单例
```

状态流：`pending` → `running` → `success` / `failed` / `timeout`

### 1.2 新 API 端点 — 添加到 `src/api/main.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tasks/import-knowledge` | 异步导入知识库（接收 file_paths 列表）→ 返回 task_id |
| POST | `/api/tasks/upload-knowledge` | 多文件上传 + 异步导入 → 返回 task_id |
| POST | `/api/tasks/import-graph` | 异步导入图谱（接收 file_path + mode）→ 返回 task_id |
| POST | `/api/tasks/upload-graph` | 图谱文件上传 + 异步导入 → 返回 task_id |
| GET | `/api/tasks/{task_id}` | 查询任务状态 |
| GET | `/api/tasks` | 任务历史列表（通知中心用）|

响应格式统一：
```json
{"success": true, "data": {"task_id": "xxx", "status": "running", ...}}
```

### 1.3 静态文件服务 — `src/api/main.py`

最后挂载（放在 API 路由之后，避免覆盖 `/api/` 路径）：

```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

### 1.4 修改点汇总

| 文件 | 改动 |
|------|------|
| `src/task_manager.py` | 新建 — 异步任务追踪系统 |
| `src/api/main.py` | 新增 6 个任务端点 + 静态文件挂载 |
| `src/api/schemas.py` | 新增 TaskResponse、TaskStatusResponse schema |
| `src/models/medica_data.py` | 可选项：添加 TaskRecord 模型持久化任务历史 |
| `requirements.txt` | 无变更（静态文件服务 use FastAPI 内置能力）|

---

## 二、前端实现

### 2.1 文件结构

```
static/
├── index.html          # 主页面（书型 UI）
├── css/
│   └── style.css       # 全部样式（书籍 3D 变换、布局、动画）
└── js/
    ├── app.js          # 主逻辑（书页切换、渲染）
    ├── api.js          # Fetch API 封装
    └── notifications.js # 通知系统（轮询 + 弹窗）
```

### 2.2 UI 布局

**书籍效果**：用 CSS 3D `perspective` + `rotateY` 模拟翻书

```
┌──────────────────────────────────────┐
│        🔔 (通知图标, fixed 右上角)     │
│                                      │
│  ┌──── 书脊 ────┐  ┌── 书页右侧 ──┐ │
│  │              │  │              │ │
│  │  [📖 问药]   │  │  (内容区域)  │ │
│  │  [📚 收录]   │  │              │ │
│  │              │  │ 根据左侧      │ │
│  │              │  │ 选择切换      │ │
│  │              │  │              │ │
│  └──────────────┘  └──────────────┘ │
│   (书页左侧: 导航)                    │
└──────────────────────────────────────┘
```

### 2.3 问药（聊天）

- 消息列表（气泡样式，用户右、AI 左）
- 底部输入框 + 发送按钮
- 调用 `POST /api/chat`
- 支持 Enter 发送

### 2.4 收录（导入）

古籍收录：
- 文件选择器（支持多文件，`accept=".md,.txt,.pdf"`）
- 分块大小/重叠 配置（可选展开）
- "开始收录"按钮 → 调用 `POST /api/tasks/upload-knowledge`
- 进度提示

图谱收录：
- 文件选择器（`.json`）
- 导入模式选择（full_import / append）
- 实体类型过滤（可选）
- "开始收录"按钮 → 调用 `POST /api/tasks/upload-graph`

### 2.5 通知系统

- 右上角铃铛图标 🔔（有未读时显示小红点）
- 点击展开下拉列表显示最近任务
- 每个任务显示：图标（✓成功 / ✗失败 / ⏳进行中）+ 文件名 + 时间 + 摘要
- 前端每 5 秒轮询 `GET /api/tasks` 获取最新状态
- 新任务完成时弹 toast 提示

### 2.6 视觉风格

- 配色：米黄色纸张背景 `#f5f0e8`、深褐色文字 `#3c2415`、朱砂红点缀 `#c0392b`
- 字体：衬线字体（`Noto Serif SC` 或系统衬线）
- 书页阴影、纸张纹理（CSS 渐变模拟）
- 古籍线装书装订线效果
- 响应式：适配桌面（大屏）/ 平板

---

## 三、实施顺序

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 1 | 创建 `task_manager.py` 异步任务系统 | 无 |
| 2 | 添加任务 API 端点 + 静态文件挂载到 `main.py` | 步骤 1 |
| 3 | 添加相关 Pydantic schemas | 步骤 2 |
| 4 | 创建 `static/` 前端文件（HTML + CSS + JS） | 步骤 2（可联调）|

---

## 四、验证方法

1. `docker compose up -d` 启动服务
2. 浏览器访问 `http://localhost:8000` → 看到书型 UI
3. 点击"问药" → 输入消息 → 得到 AI 回复
4. 点击"收录 → 古籍收录" → 选择文件 → 开始收录 → 通知铃铛出现新消息
5. 点击"收录 → 图谱收录" → 选择 JSON → 开始收录 → 查看通知结果
6. `GET /api/tasks` 返回任务列表
