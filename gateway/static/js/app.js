// Общие утилиты для работы с API

// Gateway routers live at the root (/tasks, /users, /auth), not under /api.
const API_BASE = '';

// Currently authenticated user (filled by loadCurrentUser), or null.
let currentUser = null;

// Показать уведомление
function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 0.375rem;
        background-color: ${type === 'success' ? '#10b981' : '#ef4444'};
        color: white;
        font-weight: 500;
        z-index: 9999;
        animation: slideInRight 0.3s;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Форматирование даты
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Обработка ошибок API
function handleApiError(error) {
    console.error('API Error:', error);
    showNotification(error.message || 'Произошла ошибка', 'error');
}

// --- Аутентификация (общая для всех страниц) ---

// Узнать текущего пользователя по сессионной cookie. Возвращает user|null.
// Мемоизируется: несколько вызовов на странице делят один запрос /auth/me.
let _mePromise = null;
function loadCurrentUser() {
    if (!_mePromise) {
        _mePromise = (async () => {
            try {
                const res = await fetch(`${API_BASE}/auth/me`, { credentials: 'same-origin' });
                currentUser = res.ok ? await res.json() : null;
            } catch (error) {
                currentUser = null;
            }
            window.currentUser = currentUser;
            return currentUser;
        })();
    }
    return _mePromise;
}

// Отрисовать в навбаре состояние входа (имя + выйти, либо ссылку «Войти»).
function renderAuthNav() {
    const nav = document.getElementById('auth-nav');
    if (!nav) return;
    if (currentUser) {
        nav.innerHTML =
            `<span class="nav-user">👤 ${escapeHtml(currentUser.username)}</span> ` +
            `<a href="#" onclick="logout(event)">Выйти</a>`;
    } else {
        nav.innerHTML = `<a href="/web/login">Войти</a>`;
    }
}

// Выход: гасим сессию и возвращаемся на страницу входа.
async function logout(event) {
    if (event) event.preventDefault();
    try {
        await fetch(`${API_BASE}/auth/logout`, {
            method: 'POST',
            credentials: 'same-origin',
        });
    } catch (error) {
        // ignore -- logout is best-effort
    }
    window.location.href = '/web/login';
}

// Отправить на страницу входа (например, после 401 на операции записи).
function redirectToLogin() {
    showNotification('Требуется вход в систему', 'error');
    setTimeout(() => { window.location.href = '/web/login'; }, 800);
}

// Простой HTML-эскейп (дублируется в tasks.js для автономности страницы).
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : text;
    return div.innerHTML;
}

// На каждой странице: подтянуть пользователя и отрисовать навбар.
document.addEventListener('DOMContentLoaded', async () => {
    await loadCurrentUser();
    renderAuthNav();
});

// CSS для анимаций уведомлений
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
