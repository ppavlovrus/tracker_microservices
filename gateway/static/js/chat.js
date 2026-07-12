// Общий чат: WebSocket к /ws/chat, live через Redis pub/sub на сервере.
// Виджет в правом нижнем углу; виден только вошедшим пользователям.

const CHAT_RECONNECT_BASE_MS = 1000;
const CHAT_RECONNECT_MAX_MS = 15000;

let chatSocket = null;
let chatReconnectAttempt = 0;
let chatUnread = 0;

function chatWsUrl() {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${window.location.host}/ws/chat`;
}

function initChat() {
    if (!currentUser) return; // гость: чата нет
    renderChatWidget();
    connectChat();
}

function connectChat() {
    chatSocket = new WebSocket(chatWsUrl());

    chatSocket.onopen = () => {
        chatReconnectAttempt = 0;
        setChatStatus(true);
    };

    chatSocket.onmessage = (event) => {
        let frame;
        try { frame = JSON.parse(event.data); } catch { return; }
        if (frame.type === 'ping') {
            chatSocket.send(JSON.stringify({ type: 'pong' }));
        } else if (frame.type === 'history') {
            const list = document.getElementById('chat-messages');
            list.innerHTML = '';
            frame.messages.forEach((m) => appendChatMessage(m, false));
            scrollChatToBottom();
        } else if (frame.type === 'message') {
            appendChatMessage(frame, true);
        } else if (frame.type === 'error') {
            showNotification(frame.detail || 'Ошибка чата', 'error');
        }
    };

    chatSocket.onclose = (event) => {
        setChatStatus(false);
        if (event.code === 4401) return; // сессия умерла — не долбимся
        const delay = Math.min(
            CHAT_RECONNECT_BASE_MS * 2 ** chatReconnectAttempt,
            CHAT_RECONNECT_MAX_MS
        );
        chatReconnectAttempt += 1;
        setTimeout(connectChat, delay);
    };
}

function sendChatMessage(event) {
    event.preventDefault();
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text || !chatSocket || chatSocket.readyState !== WebSocket.OPEN) return;
    chatSocket.send(JSON.stringify({ type: 'message', text }));
    input.value = '';
}

function appendChatMessage(message, live) {
    const list = document.getElementById('chat-messages');
    if (!list) return;
    const mine = currentUser && message.user_id === currentUser.id;
    const item = document.createElement('div');
    item.className = `chat-message${mine ? ' chat-message-mine' : ''}`;
    item.innerHTML =
        `<span class="chat-message-author">${escapeHtml(message.username)}</span>` +
        `<span class="chat-message-time">${formatDate(message.ts)}</span>` +
        `<div class="chat-message-text">${escapeHtml(message.text)}</div>`;
    list.appendChild(item);
    if (live) {
        scrollChatToBottom();
        const panel = document.getElementById('chat-panel');
        if (panel.style.display === 'none' && !mine) {
            chatUnread += 1;
            updateChatBadge();
        }
    }
}

function scrollChatToBottom() {
    const list = document.getElementById('chat-messages');
    if (list) list.scrollTop = list.scrollHeight;
}

function toggleChat() {
    const panel = document.getElementById('chat-panel');
    const opened = panel.style.display === 'none';
    panel.style.display = opened ? 'flex' : 'none';
    if (opened) {
        chatUnread = 0;
        updateChatBadge();
        scrollChatToBottom();
        document.getElementById('chat-input').focus();
    }
}

function updateChatBadge() {
    const badge = document.getElementById('chat-badge');
    badge.textContent = chatUnread;
    badge.style.display = chatUnread > 0 ? 'inline-block' : 'none';
}

function setChatStatus(online) {
    const dot = document.getElementById('chat-status');
    if (dot) dot.style.background = online ? '#10b981' : '#ef4444';
}

function renderChatWidget() {
    const widget = document.createElement('div');
    widget.id = 'chat-widget';
    widget.innerHTML = `
        <div id="chat-panel" style="display: none;">
            <div id="chat-header">
                <span id="chat-status"></span>
                <span>Общий чат</span>
                <button id="chat-close" onclick="toggleChat()">&times;</button>
            </div>
            <div id="chat-messages"></div>
            <form id="chat-form" onsubmit="sendChatMessage(event)">
                <input type="text" id="chat-input" class="input"
                       placeholder="Сообщение..." maxlength="1000" autocomplete="off">
                <button type="submit" class="btn btn-primary">➤</button>
            </form>
        </div>
        <button id="chat-toggle" class="btn btn-primary" onclick="toggleChat()">
            💬 Чат <span id="chat-badge" style="display: none;"></span>
        </button>
    `;
    document.body.appendChild(widget);

    const style = document.createElement('style');
    style.textContent = `
        #chat-widget { position: fixed; right: 20px; bottom: 20px; z-index: 1000;
            display: flex; flex-direction: column; align-items: flex-end; gap: 0.5rem; }
        #chat-panel { display: flex; flex-direction: column; width: 320px; height: 420px;
            background: #fff; border: 1px solid #e5e7eb; border-radius: 0.5rem;
            box-shadow: 0 10px 25px rgba(0,0,0,0.15); overflow: hidden; }
        #chat-header { display: flex; align-items: center; gap: 0.5rem;
            padding: 0.6rem 0.8rem; background: #1f2937; color: #fff; font-weight: 600; }
        #chat-status { width: 9px; height: 9px; border-radius: 50%; background: #ef4444; }
        #chat-close { margin-left: auto; background: none; border: none; color: #fff;
            font-size: 1.1rem; cursor: pointer; }
        #chat-messages { flex: 1; overflow-y: auto; padding: 0.6rem;
            display: flex; flex-direction: column; gap: 0.5rem; background: #f9fafb; }
        .chat-message { max-width: 85%; align-self: flex-start; background: #fff;
            border: 1px solid #e5e7eb; border-radius: 0.5rem; padding: 0.4rem 0.6rem;
            font-size: 0.875rem; }
        .chat-message-mine { align-self: flex-end; background: #eff6ff; }
        .chat-message-author { font-weight: 600; margin-right: 0.4rem; }
        .chat-message-time { color: #9ca3af; font-size: 0.7rem; }
        .chat-message-text { white-space: pre-wrap; word-break: break-word; }
        #chat-form { display: flex; gap: 0.4rem; padding: 0.5rem;
            border-top: 1px solid #e5e7eb; background: #fff; }
        #chat-form .input { flex: 1; }
        #chat-badge { background: #ef4444; color: #fff; border-radius: 9999px;
            padding: 0 0.4rem; font-size: 0.75rem; margin-left: 0.3rem; }
    `;
    document.head.appendChild(style);
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadCurrentUser();
    initChat();
});
