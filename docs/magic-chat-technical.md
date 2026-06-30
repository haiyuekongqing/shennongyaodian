# 灵境问药 — 玄幻漂浮书页技术方案

> 一个零外部依赖的玄幻风格漂浮书页问答界面，作为主药典 UI 的补充页面。

## 概述

- **访问地址**: `http://localhost:8000/magic`
- **定位**: 纯问答页面，无管理功能，用作沉浸式问药体验
- **风格**: 玄幻/修仙风 — 夜空、星尘、金色漂浮书、粒子特效
- **技术原则**: 零外部 CDN 依赖，全部原生实现

---

## 技术栈

| 技术 | 用途 | 文件位置 |
|------|------|---------|
| **CSS 3D Transforms** | 封面翻书动画 | `static/magic/index.html` `<style>` 内 |
| **CSS Keyframes** | 书籍漂浮、星空闪烁、粒子上升 | 同上 |
| **CSS Gradients** | 夜空背景、魔法光晕、封面质感 | 同上 |
| **CSS Custom Properties** | 粒子随机位置/大小/延迟 | 同上 |
| **Vanilla JS (Fetch API)** | 聊天交互、DOM 渲染 | 同上 `<script>` 内 |
| **CSS Pseudo-elements** | 封面四角装饰、书脊线、卷角 | 同上 |

**无任何外部库** — 不依赖 StPageFlip、Alpine.js、tsparticles、jQuery 等

---

## 架构说明

### 页面路由

```
请求 GET /magic
  └── FastAPI StaticFiles (html=True)
       └── static/magic/index.html
```

利用 FastAPI `StaticFiles` 的 `html=True` 特性，`/magic` 自动映射到 `static/magic/index.html`，无需额外路由代码。

### 页面结构

```
body
├── .stars (80 个随机星点)
├── .particles (20 个上升粒子)
├── .glow-floor (底部光晕)
├── .back-link (返回药典)
├── .magic-scene (主场景)
│   └── .book-wrapper (漂浮容器)
│       └── .book-inner (3D 容器)
│           ├── .book-cover (封面, z-index:2)
│           │   ├── .corner (四角装饰 x4)
│           │   ├── .cover-stars (封面上星点 x12)
│           │   └── .cover-content (标题 + 提示)
│           └── .book-inside (翻开后内容)
│               ├── .book-left (左页: 古籍引用)
│               └── .book-right (右页: 聊天区域)
│                   ├── .chat-title
│                   ├── .chat-messages
│                   └── .chat-input-row
└── .magic-footer
```

### 动画系统

| 动画 | 触发 | 实现 |
|------|------|------|
| 星空闪烁 | 自动 | 80 个 `.star` 元素，`--d` 自定义属性控制周期 |
| 粒子上升 | 自动 | 20 个 `.particle` 元素，`floatUp` keyframes |
| 底部光晕脉动 | 自动 | `pulseGlow` keyframes |
| 书籍漂浮 | 自动 | `floatBook` keyframes, `translateY(-18px)` |
| 阴影跟随 | 自动 | `shadowFloat` keyframes, 与漂浮同步 |
| 封面翻开 | 点击封面 | `transform: rotateY(-175deg)` + `1s cubic-bezier` |
| 提示文字闪烁 | 自动 | `pulseHint` keyframes |

### 翻书原理

使用 CSS 3D 变换实现翻书效果，无需 StPageFlip：

```css
.book-inner {
    transform-style: preserve-3d;
}
.book-cover {
    backface-visibility: hidden;
    transform-origin: left center;
    transition: transform 1s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 2;
}
.book-inner.open .book-cover {
    transform: rotateY(-175deg);
}
```

封面以左边缘为轴心旋转 175°，露出下方的内容页。`cubic-bezier` 缓动函数模拟真实纸张翻折的加速-减速效果。

### 粒子系统（纯 CSS）

粒子使用 CSS 自定义属性实现随机化，无需 tsparticles：

```css
.particle {
    width: var(--size);
    height: var(--size);
    background: var(--color);
    box-shadow: 0 0 var(--glow) var(--color);
    animation: floatUp var(--duration) ease-in-out infinite;
    animation-delay: var(--delay);
    left: var(--x);
}

@keyframes floatUp {
    0%   { transform: translateY(100vh) scale(0); opacity: 0; }
    10%  { opacity: var(--opacity); }
    90%  { opacity: var(--opacity); }
    100% { transform: translateY(-10vh) translateX(var(--drift)) scale(1); opacity: 0; }
}
```

JS 生成 20 个粒子，每个赋予随机的位置(`--x`)、大小(`--size`)、颜色(`--color`)、周期(`--duration`)、延迟(`--delay`)和漂移量(`--drift`)。

### 聊天 API

与主界面共用同一个后端接口：

```
POST /api/chat
Content-Type: application/json

{"message": "人参有什么功效？", "session_id": "magic_xxx"}
```

JS 中通过 `fetch('/api/chat', ...)` 调用，无任何中间层封装。

---

## 配色方案

| 用途 | 颜色 | CSS 变量 |
|------|------|----------|
| 夜空顶层 | `#0a0a2e` | `--night-1` |
| 夜空中层 | `#150a2e` | `--night-2` |
| 夜空底层 | `#1f0a3a` | `--night-3` |
| 金色 | `#ffd700` | `--gold` |
| 金色发光 | `#ffec8b` | `--gold-glow` |
| 金色暗调 | `#b8962e` | `--gold-dim` |
| 魔法紫 | `#a78bfa` | `--magic` |
| 魔法深紫 | `#7c3aed` | `--magic-deep` |
| 封面底色 | `#1a0e1a` | `--cover-dark` |
| 内页纸色 | `#f5f0e8` | `--parchment` |
| 文字墨色 | `#3c2415` | `--ink` |

---

## 与主界面的关系

| 维度 | 主界面 (`/`) | 灵境页面 (`/magic`) |
|------|-------------|-------------------|
| 定位 | 完整功能药典 | 沉浸式问答 |
| 用户 | 游客 + 管理员 | 所有访客 |
| 功能 | 问答 + 收录 + 系统状态 | 仅问答 |
| 风格 | 古籍线装书 | 玄幻漂浮书 |
| 认证 | 管理员登录 | 无认证 |
| 依赖 | 零外部依赖 | 零外部依赖 |

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `static/magic/index.html` | 页面文件（含全部 HTML/CSS/JS）|
| `src/api/main.py` | FastAPI 主应用（无需修改，利用 StaticFiles 自动路由） |

---

**更新时间**: 2026-06-18
