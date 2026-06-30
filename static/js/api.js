/**
 * 神农本草 — API 客户端
 */
var API = {
    chat: function (message, sessionId) {
        return fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message, session_id: sessionId || null }),
        }).then(function (r) { return r.json(); });
    },

    knowledgeStatus: function () {
        return fetch('/api/knowledge/status').then(function (r) { return r.json(); });
    },

    graphStats: function () {
        return fetch('/api/graph/stats').then(function (r) {
            if (!r.ok) return null;
            return r.json();
        });
    },

    uploadKnowledge: function (files, chunkSize, overlap, token) {
        var form = new FormData();
        for (var i = 0; i < files.length; i++) form.append('files', files[i]);
        form.append('chunk_size', String(chunkSize));
        form.append('overlap', String(overlap));
        var headers = {};
        if (token) headers['Authorization'] = 'Bearer ' + token;
        return fetch('/api/tasks/upload-knowledge', {
            method: 'POST',
            headers: headers,
            body: form,
        }).then(function (r) { return r.json(); });
    },

    uploadGraph: function (file, mode, entityTypes, token) {
        var form = new FormData();
        form.append('file', file);
        form.append('mode', mode);
        if (entityTypes) form.append('entity_types', entityTypes);
        var headers = {};
        if (token) headers['Authorization'] = 'Bearer ' + token;
        return fetch('/api/tasks/upload-graph', {
            method: 'POST',
            headers: headers,
            body: form,
        }).then(function (r) { return r.json(); });
    },

    listTasks: function (limit) {
        return fetch('/api/tasks?limit=' + (limit || 50)).then(function (r) { return r.json(); });
    },
};
