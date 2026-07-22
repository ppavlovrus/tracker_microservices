// Live-уведомления о задачах через Server-Sent Events (/sse/tasks).
// Односторонний поток: сервер шлёт task.created/updated/deleted, браузер
// показывает тост и обновляет доску. Только для вошедших пользователей.
//
// Переподключение делает сам EventSource. Исключение — если сессия умерла,
// сервер отвечает 401: по спецификации EventSource в этом случае закрывается
// без ретраев, так что мы не долбим сервер впустую.

let taskEventSource = null;
let boardRefreshTimer = null;

function initTaskEvents() {
    if (!window.currentUser) return; // гость: уведомлений нет
    if (taskEventSource) return;     // уже подключены

    taskEventSource = new EventSource('/sse/tasks', { withCredentials: true });

    taskEventSource.addEventListener('task.created', (e) => {
        const task = parseTaskEvent(e);
        showNotification(`📌 Новая задача: «${task.title || 'без названия'}»`);
        scheduleBoardRefresh();
    });

    taskEventSource.addEventListener('task.updated', (e) => {
        const task = parseTaskEvent(e);
        const title = task.title ? `: «${task.title}»` : '';
        showNotification(`✏️ Задача обновлена${title}`);
        scheduleBoardRefresh();
    });

    taskEventSource.addEventListener('task.deleted', () => {
        showNotification('🗑️ Задача удалена');
        scheduleBoardRefresh();
    });

    taskEventSource.onerror = () => {
        // readyState CLOSED => сервер отверг поток (например, 401): не ретраим.
        if (taskEventSource.readyState === EventSource.CLOSED) {
            taskEventSource = null;
        }
        // Иначе EventSource сам переподключится — ничего не делаем.
    };
}

// Достаём объект задачи из кадра события. У событий по тегам поля task нет
// (только id) — возвращаем пустой объект, тост обойдётся без названия.
function parseTaskEvent(event) {
    try {
        const data = JSON.parse(event.data);
        return data.task || {};
    } catch {
        return {};
    }
}

// Дебаунс: пачка событий (например, массовое изменение) перерисует доску один
// раз. На страницах без доски loadTasks нет — просто ничего не делаем.
function scheduleBoardRefresh() {
    if (typeof window.loadTasks !== 'function') return;
    clearTimeout(boardRefreshTimer);
    boardRefreshTimer = setTimeout(() => window.loadTasks(), 300);
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadCurrentUser();
    initTaskEvents();
});
