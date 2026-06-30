/**
 * 神农本草 — 应用主逻辑（纯原生 JS）
 * 支持游客/管理员双模式
 */
(function () {
    'use strict';

    // ── 状态 ──────────────────────────────────────
    var state = {
        page: 'ask',
        sessionId: 'ui_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
        isAdmin: false,
        token: '',

        // 聊天
        messages: [],
        isSending: false,

        // 知识上传
        knowledgeFiles: [],
        isUploadingKnowledge: false,

        // 图谱上传
        graphFile: null,
        isUploadingGraph: false,

        // 通知
        tasks: [],
        showNotifications: false,
        unreadCount: 0,
        toasts: [],
        // 时序
        lastTiming: null,
        showTiming: false,
    };

    // ── DOM 工具 ──────────────────────────────────
    function byId(id) { return document.getElementById(id); }

    function esc(str) {
        var d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    function formatTime(isoStr) {
        if (!isoStr) return '';
        var d = new Date(isoStr);
        var now = new Date();
        var diff = now - d;
        if (diff < 60000) return '刚刚';
        if (diff < 3600000) return Math.floor(diff / 60000) + ' 分钟前';
        if (diff < 86400000) return Math.floor(diff / 3600000) + ' 小时前';
        return (d.getMonth() + 1) + '/' + d.getDate() + ' ' +
            String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    }

    function taskIcon(status) {
        return { pending: '⏳', running: '🔄', success: '✅', failed: '❌', timeout: '⏰' }[status] || '❓';
    }

    // ── 认证 ──────────────────────────────────────
    function toggleAuth() {
        if (state.isAdmin) {
            logout();
        } else {
            showLogin();
        }
    }

    function showLogin() {
        byId('login-overlay').classList.remove('hidden');
        byId('login-error').classList.add('hidden');
        byId('login-username').value = '';
        byId('login-password').value = '';
        byId('login-username').focus();
    }

    function hideLogin() {
        byId('login-overlay').classList.add('hidden');
    }

    function login() {
        var username = byId('login-username').value.trim();
        var password = byId('login-password').value.trim();
        if (!username || !password) return;

        var btn = byId('login-overlay').querySelector('button');
        btn.textContent = '登录中…';
        btn.disabled = true;

        fetch('/api/admin/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username, password: password }),
        })
        .then(function (r) { return r.json(); })
        .then(function (res) {
            if (res.success && res.token) {
                state.isAdmin = true;
                state.token = res.token;
                localStorage.setItem('admin_token', res.token);
                hideLogin();
                applyAuthState();
                showToast('success', '欢迎回来，' + username);
            } else {
                byId('login-error').textContent = res.message || '用户名或密码错误';
                byId('login-error').classList.remove('hidden');
            }
        })
        .catch(function (e) {
            byId('login-error').textContent = '网络错误：' + e.message;
            byId('login-error').classList.remove('hidden');
        })
        .finally(function () {
            btn.textContent = '登 录';
            btn.disabled = false;
        });
    }

    function logout() {
        if (state.token) {
            fetch('/api/admin/logout', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + state.token },
            }).catch(function () {});
        }
        state.isAdmin = false;
        state.token = '';
        localStorage.removeItem('admin_token');
        applyAuthState();
        // 如果在管理页面，切回问药
        if (state.page !== 'ask') {
            navigate('ask');
        }
        showToast('info', '已退出管理');
    }

    function applyAuthState() {
        // 导航项可见性
        byId('nav-collect').classList.toggle('hidden', !state.isAdmin);
        byId('nav-status').classList.toggle('hidden', !state.isAdmin);
        // 通知铃铛
        byId('notif-bell').classList.toggle('hidden', !state.isAdmin);
        // 时序按钮（用 style.display 确保硬生效）
        byId('timing-btn').style.display = state.isAdmin ? '' : 'none';
        // 底部状态
        byId('guest-label').classList.toggle('hidden', state.isAdmin);
        byId('admin-label').classList.toggle('hidden', !state.isAdmin);
        byId('auth-action').textContent = state.isAdmin ? '退出登录' : '管理员登录';
    }

    function tryRestoreToken() {
        var token = localStorage.getItem('admin_token');
        if (!token) return;
        // 验证 token 是否有效
        state.token = token;
        fetch('/api/admin/info', {
            headers: { 'Authorization': 'Bearer ' + token }
        })
        .then(function (r) {
            if (r.ok) {
                state.isAdmin = true;
                applyAuthState();
            } else {
                localStorage.removeItem('admin_token');
                state.token = '';
            }
        })
        .catch(function () {
            localStorage.removeItem('admin_token');
            state.token = '';
        });
    }

    // ── 导航 ──────────────────────────────────────
    function navigate(page) {
        state.page = page;
        document.querySelectorAll('.nav-item').forEach(function (el) {
            var p = el.getAttribute('data-page');
            el.classList.toggle('active', p === page || (page.indexOf('collect') === 0 && p === 'collect'));
        });
        document.querySelectorAll('.page-content').forEach(function (el) {
            el.classList.toggle('hidden', el.id !== 'page-' + page);
        });
        closeNotifications();
        document.querySelectorAll('.sub-tab').forEach(function (el) {
            el.classList.toggle('active', el.getAttribute('data-page') === page);
        });
        if (page === 'status' && state.isAdmin) loadStats();
        updateUploadBtn();
        updateGraphBtn();
    }

    // ── 聊天 ──────────────────────────────────────
    function sendMessage() {
        var input = byId('chat-input');
        var msg = input.value.trim();
        if (!msg || state.isSending) return;

        input.value = '';
        state.isSending = true;
        state.messages.push({ role: 'user', content: msg });
        state.messages.push({ role: 'assistant', content: '', loading: true });
        renderChat();

        API.chat(msg, state.sessionId).then(function (res) {
            var last = state.messages[state.messages.length - 1];
            last.loading = false;
            last.content = res.answer || '（未收到回复）';
            last.disclaimer = res.disclaimer || '';
            state.isSending = false;
            // 存储时序
            if (res.timing && res.timing.length) {
                state.lastTiming = res.timing;
                var total = res.timing[res.timing.length - 1].elapsed_s || 0;
                var tbtn = byId('timing-btn');
                tbtn.innerHTML = '⏱ ' + total.toFixed(1) + 's';
                if (state.isAdmin) tbtn.style.display = '';
            }
            renderChat();
            byId('chat-messages').scrollTop = byId('chat-messages').scrollHeight;
        }).catch(function (e) {
            var last = state.messages[state.messages.length - 1];
            last.loading = false;
            last.content = '请求失败：' + e.message;
            state.isSending = false;
            renderChat();
        });
    }

    function renderChat() {
        var box = byId('chat-messages');
        if (state.messages.length === 0) {
            box.innerHTML =
                '<div class="chat-empty">' +
                '<div class="chat-empty-icon">🏛️</div>' +
                '<div class="chat-empty-text">神农尝百草，我来解君疑</div>' +
                '<div class="chat-empty-hint">输入药材名、症状或方剂，开始咨询</div>' +
                '</div>';
            return;
        }
        box.innerHTML = state.messages.map(function (msg) {
            var body, disc = '';
            if (msg.loading) {
                body = '<span class="typing-dots"><span></span><span></span><span></span></span>';
            } else {
                body = esc(msg.content);
                if (msg.disclaimer) disc = '<span class="disclaimer">' + esc(msg.disclaimer) + '</span>';
            }
            return '<div class="chat-bubble ' + msg.role + '">' + body + disc + '</div>';
        }).join('');
    }

    function handleChatKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    }

    // ── 知识上传 ──────────────────────────────────
    function handleKnowledgeFiles(e) {
        state.knowledgeFiles = Array.from(e.target.files);
        renderKnowledgeFiles();
        updateUploadBtn();
    }

    function removeKnowledgeFile(i) {
        state.knowledgeFiles.splice(i, 1);
        byId('knowledge-file-input').value = '';
        renderKnowledgeFiles();
        updateUploadBtn();
    }

    function renderKnowledgeFiles() {
        var list = byId('knowledge-file-list');
        if (state.knowledgeFiles.length === 0) {
            list.innerHTML = '';
            list.classList.add('hidden');
            return;
        }
        list.classList.remove('hidden');
        list.innerHTML = state.knowledgeFiles.map(function (f, i) {
            return '<div class="upload-file-item">' +
                '<span class="file-name">📄 ' + esc(f.name) + '</span>' +
                '<span class="file-remove" onclick="App.removeKnowledgeFile(' + i + ')">✕</span>' +
                '</div>';
        }).join('');
    }

    function updateUploadBtn() {
        var btn = byId('btn-upload-knowledge');
        if (!btn) return;
        btn.disabled = state.knowledgeFiles.length === 0 || state.isUploadingKnowledge;
        btn.textContent = state.isUploadingKnowledge ? '收录中…' : '开始收录';
        btn.classList.toggle('processing', state.isUploadingKnowledge);
    }

    function uploadKnowledge() {
        if (state.knowledgeFiles.length === 0 || state.isUploadingKnowledge) return;
        var cs = parseInt(byId('knowledge-chunk-size').value) || 500;
        var ov = parseInt(byId('knowledge-overlap').value) || 50;

        state.isUploadingKnowledge = true;
        updateUploadBtn();

        API.uploadKnowledge(state.knowledgeFiles, cs, ov, state.token).then(function (res) {
            if (res.success) {
                showToast('success', '古籍收录任务已提交（' + state.knowledgeFiles.length + ' 个文件）');
                state.unreadCount++;
                updateNotifBadge();
            } else {
                showToast('error', '提交失败：' + (res.message || '未知错误'));
                if (res.detail === '未登录' || res.detail === '令牌已过期或无效') {
                    logout();
                    showToast('error', '登录已过期，请重新登录');
                }
            }
            state.knowledgeFiles = [];
            byId('knowledge-file-input').value = '';
            renderKnowledgeFiles();
            state.isUploadingKnowledge = false;
            updateUploadBtn();
        }).catch(function (e) {
            showToast('error', '上传失败：' + e.message);
            state.isUploadingKnowledge = false;
            updateUploadBtn();
        });
    }

    // ── 图谱上传 ──────────────────────────────────
    function handleGraphFile(e) {
        var files = e.target.files;
        state.graphFile = files.length > 0 ? files[0] : null;
        renderGraphFile();
        updateGraphBtn();
    }

    function removeGraphFile() {
        state.graphFile = null;
        byId('graph-file-input').value = '';
        renderGraphFile();
        updateGraphBtn();
    }

    function renderGraphFile() {
        var list = byId('graph-file-list');
        if (!state.graphFile) {
            list.innerHTML = '';
            list.classList.add('hidden');
            return;
        }
        list.classList.remove('hidden');
        list.innerHTML =
            '<div class="upload-file-item">' +
            '<span class="file-name">🕸️ ' + esc(state.graphFile.name) + '</span>' +
            '<span class="file-remove" onclick="App.removeGraphFile()">✕</span>' +
            '</div>';
    }

    function updateGraphBtn() {
        var btn = byId('btn-upload-graph');
        if (!btn) return;
        btn.disabled = !state.graphFile || state.isUploadingGraph;
        btn.textContent = state.isUploadingGraph ? '收录中…' : '开始收录';
        btn.classList.toggle('processing', state.isUploadingGraph);
    }

    function uploadGraph() {
        if (!state.graphFile || state.isUploadingGraph) return;
        var mode = byId('graph-mode').value;
        var et = byId('graph-entity-types').value || null;

        state.isUploadingGraph = true;
        updateGraphBtn();

        API.uploadGraph(state.graphFile, mode, et, state.token).then(function (res) {
            if (res.success) {
                showToast('success', '图谱收录任务已提交（' + state.graphFile.name + '）');
                state.unreadCount++;
                updateNotifBadge();
            } else {
                showToast('error', '提交失败：' + (res.message || '未知错误'));
                if (res.detail === '未登录' || res.detail === '令牌已过期或无效') {
                    logout();
                    showToast('error', '登录已过期，请重新登录');
                }
            }
            state.graphFile = null;
            byId('graph-file-input').value = '';
            renderGraphFile();
            state.isUploadingGraph = false;
            updateGraphBtn();
        }).catch(function (e) {
            showToast('error', '上传失败：' + e.message);
            state.isUploadingGraph = false;
            updateGraphBtn();
        });
    }

    // ── 系统状态 ──────────────────────────────────
    function loadStats() {
        var area = byId('status-content');
        area.innerHTML = '<div class="chat-empty"><div class="chat-empty-icon">⏳</div><div class="chat-empty-text">加载中…</div></div>';

        Promise.all([
            API.knowledgeStatus(),
            API.graphStats(),
        ]).then(function (results) {
            var stats = results[0];
            var g = results[1];
            var html = '<div class="stats-grid">' +
                statCard('🧬', stats.num_entities ?? '—', '向量数量') +
                statCard('📦', stats.total_chunks ?? '—', '知识分块') +
                statCard('🧠', stats.embedding_model ?? '—', 'Embedding 模型') +
                statCard('📁', stats.collection_name ?? '—', '集合名称') +
                '</div>';

            if (g) {
                html += '<div style="font-family:var(--font-serif);font-size:16px;font-weight:700;margin:16px 0 8px;color:var(--ink);">🕸️ 知识图谱</div>' +
                    '<div class="stats-grid" style="grid-template-columns:1fr 1fr;">' +
                    statCard('🏷️', g.total_nodes ?? '—', '总节点数') +
                    statCard('🔗', g.total_relationships ?? '—', '总关系数') +
                    '</div>';
                if (g.node_types && g.node_types.length) {
                    html += '<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr>' +
                        '<th style="padding:6px 10px;text-align:left;border-bottom:1px solid #e0d6c8;font-size:11px;color:var(--ink-faded);">节点类型</th>' +
                        '<th style="padding:6px 10px;text-align:left;border-bottom:1px solid #e0d6c8;font-size:11px;color:var(--ink-faded);">数量</th></tr></thead><tbody>';
                    g.node_types.forEach(function (nt) {
                        html += '<tr><td style="padding:6px 10px;border-bottom:1px solid #e0d6c8;">' + esc(nt.type || nt.label) + '</td>' +
                            '<td style="padding:6px 10px;border-bottom:1px solid #e0d6c8;">' + nt.count + '</td></tr>';
                    });
                    html += '</tbody></table>';
                }
            }
            area.innerHTML = html;
        }).catch(function () {
            area.innerHTML = '<div class="chat-empty"><div class="chat-empty-icon">❌</div><div class="chat-empty-text">加载失败，请确认服务正常运行</div></div>';
        });
    }

    function statCard(icon, value, label) {
        return '<div class="stat-card">' +
            '<div class="stat-card-icon">' + icon + '</div>' +
            '<div class="stat-card-value">' + value + '</div>' +
            '<div class="stat-card-label">' + label + '</div>' +
            '</div>';
    }

    // ── 通知 ──────────────────────────────────────
    function toggleNotifications() {
        state.showNotifications = !state.showNotifications;
        if (state.showNotifications) {
            state.unreadCount = 0;
            updateNotifBadge();
            pollTasks();
        }
        byId('notification-dropdown').classList.toggle('hidden', !state.showNotifications);
        byId('notif-overlay').classList.toggle('hidden', !state.showNotifications);
    }

    function closeNotifications() {
        state.showNotifications = false;
        byId('notification-dropdown').classList.add('hidden');
        byId('notif-overlay').classList.add('hidden');
    }

    function updateNotifBadge() {
        var badge = byId('notif-badge');
        if (state.unreadCount > 0) {
            badge.textContent = state.unreadCount;
            badge.style.display = 'flex';
        } else {
            badge.style.display = 'none';
        }
    }

    function renderNotifications() {
        var list = byId('notif-list');
        if (state.tasks.length === 0) {
            list.innerHTML = '<div class="notification-empty">暂无导入记录</div>';
            return;
        }
        list.innerHTML = state.tasks.map(function (t) {
            return '<div class="notification-item">' +
                '<span class="notification-status-icon">' + taskIcon(t.status) + '</span>' +
                '<div class="notification-content">' +
                '<div class="notification-title">' + esc((t.file_names || []).join(', ')) + '</div>' +
                '<div class="notification-message">' + esc(t.message || t.status) + '</div>' +
                '<div class="notification-time">' + formatTime(t.completed_at || t.created_at || '') + '</div>' +
                '</div></div>';
        }).join('');
    }

    function pollTasks() {
        API.listTasks(50).then(function (res) {
            if (!res.success || !Array.isArray(res.data)) return;
            var prevLen = state.tasks.length;
            state.tasks = res.data;
            renderNotifications();

            if (prevLen > 0 && res.data.length > prevLen) {
                res.data.slice(0, res.data.length - prevLen).forEach(function (t) {
                    if (t.status === 'success' || t.status === 'failed' || t.status === 'timeout') {
                        showToast(t.status === 'success' ? 'success' : 'error',
                            (t.status === 'success' ? '✅ ' : '❌ ') +
                            (t.file_names || []).join(', ') + ' — ' + (t.message || t.status)
                        );
                        state.unreadCount++;
                        updateNotifBadge();
                    }
                });
            }
        }).catch(function () {});
    }

    // ── Toast ─────────────────────────────────────
    function showToast(type, message) {
        var id = Date.now() + Math.random();
        state.toasts.push({ id: id, type: type, message: message });
        renderToasts();
        setTimeout(function () {
            state.toasts = state.toasts.filter(function (t) { return t.id !== id; });
            renderToasts();
        }, 4000);
    }

    function renderToasts() {
        var container = byId('toast-container');
        if (state.toasts.length === 0) {
            container.innerHTML = '';
            return;
        }
        container.innerHTML = state.toasts.map(function (t) {
            return '<div class="toast ' + t.type + '">' + esc(t.message) + '</div>';
        }).join('');
    }

    // ── 暴露到全局 ────────────────────────────────
    window.App = {
        navigate: navigate,
        handleChatKeydown: handleChatKeydown,
        sendMessage: sendMessage,
        handleKnowledgeFiles: handleKnowledgeFiles,
        removeKnowledgeFile: removeKnowledgeFile,
        uploadKnowledge: uploadKnowledge,
        handleGraphFile: handleGraphFile,
        removeGraphFile: removeGraphFile,
        uploadGraph: uploadGraph,
        toggleNotifications: toggleNotifications,
        closeNotifications: closeNotifications,
        markAllRead: function () { state.unreadCount = 0; updateNotifBadge(); },
        toggleAuth: toggleAuth,
        login: login,
        toggleTiming: function () {
            state.showTiming = !state.showTiming;
            console.log('toggleTiming:', state.showTiming, state.lastTiming);
            try { renderTiming(); } catch(e) { console.error('renderTiming error:', e); }
        },
    };

    // ── 时序面板 ──────────────────────────────────
    function renderTiming() {
        var panel = byId('timing-panel');
        var overlay = byId('timing-overlay');
        if (!state.showTiming) {
            panel.classList.add('hidden');
            overlay.classList.add('hidden');
            return;
        }
        panel.classList.remove('hidden');
        overlay.classList.remove('hidden');

        if (!state.lastTiming || !state.lastTiming.length) {
            panel.innerHTML =
                '<div class="content-title" style="font-size:16px;margin-bottom:16px;">⏱ 请求时序</div>' +
                '<div style="text-align:center;padding:20px 0;color:var(--ink-faded);font-size:13px;">暂无数据<br><span style="font-size:11px;opacity:0.6;">发送问题后自动记录</span></div>';
            return;
        }

        var html = '<div class="content-title" style="font-size:16px;margin-bottom:16px;">⏱ 请求时序</div>';
        html += '<div style="margin-bottom:12px;font-size:12px;color:var(--ink-faded);">各阶段耗时（点击空白关闭）</div>';

        var total = state.lastTiming[state.lastTiming.length - 1].elapsed_s || 1;

        for (var i = 0; i < state.lastTiming.length; i++) {
            var t = state.lastTiming[i];
            if (t.since_last_s < 0.05 && t.phase !== 'search' && t.phase !== 'llm') continue;
            if (t.phase === 'start') continue;
            var pct = Math.min(100, Math.max(3, (t.since_last_s / total) * 100));
            var color = '#5b8c6f';
            if (t.phase === 'llm') color = '#c0392b';
            if (t.phase === 'search') color = '#7c3aed';
            html += '<div style="margin-bottom:10px;">';
            html += '<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">';
            html += '<span style="color:var(--ink);font-weight:600;">' + phaseLabel(t.phase) + '</span>';
            html += '<span style="color:var(--ink-faded);">' + t.since_last_s.toFixed(1) + 's</span>';
            html += '</div>';
            html += '<div style="height:14px;background:var(--parchment-dark);border-radius:3px;overflow:hidden;">';
            html += '<div style="height:100%;width:' + pct + '%;background:' + color + ';border-radius:3px;transition:width 0.3s;"></div>';
            html += '</div></div>';
        }

        html += '<div style="margin-top:14px;padding-top:10px;border-top:1px solid var(--parchment-shadow);display:flex;justify-content:space-between;font-size:13px;">';
        html += '<span style="color:var(--ink);font-weight:700;">总计</span>';
        html += '<span style="color:var(--ink);font-weight:700;">' + total.toFixed(1) + 's</span>';
        html += '</div>';

        panel.innerHTML = html;
    }

    function phaseLabel(phase) {
        var labels = {
            search: '向量检索',
            llm: 'LLM 推理',
            intent: '意图识别',
            retrieval: '混合检索',
            fallback: '降级处理',
        };
        return labels[phase] || phase;
    }

    // 初始化时序按钮显示
    function initTimingBtn() {
        var btn = byId('timing-btn');
        if (btn && state.lastTiming) {
            var total = state.lastTiming[state.lastTiming.length - 1].elapsed_s || 0;
            btn.innerHTML = '⏱ ' + total.toFixed(1) + 's';
        }
    }

    // ── 启动 ──────────────────────────────────────
    function init() {
        tryRestoreToken();
        applyAuthState();
        navigate('ask');
        initTimingBtn();
        // 通知轮询只对管理员有意义，但有 token 时才轮询
        if (localStorage.getItem('admin_token')) {
            pollTasks();
            setInterval(pollTasks, 5000);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
