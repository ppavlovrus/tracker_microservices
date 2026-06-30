// Управление задачами (Kanban-доска)

let allTasks = [];

// Колонки доски = статусы задач. Порядок задаёт порядок колонок.
const STATUSES = [
    { id: 1, name: 'Новая' },
    { id: 2, name: 'В работе' },
    { id: 3, name: 'Завершена' },
];

// Загрузка задач
async function loadTasks() {
    try {
        const searchQuery = document.getElementById('search')?.value.toLowerCase();

        const response = await fetch(`${API_BASE}/tasks?limit=100`);
        if (!response.ok) throw new Error('Ошибка загрузки задач');

        const data = await response.json();
        allTasks = data.tasks || [];

        // Поиск по названию/описанию (колонки сами фильтруют по статусу).
        let filteredTasks = allTasks;
        if (searchQuery) {
            filteredTasks = filteredTasks.filter(t =>
                t.title.toLowerCase().includes(searchQuery) ||
                (t.description && t.description.toLowerCase().includes(searchQuery))
            );
        }

        displayTasks(filteredTasks);
    } catch (error) {
        handleApiError(error);
    }
}

// Отрисовка Kanban-доски: по колонке на каждый статус.
function displayTasks(tasks) {
    const container = document.getElementById('tasks-container');
    const loggedIn = !!window.currentUser;
    container.className = 'kanban-board';

    container.innerHTML = STATUSES.map(status => {
        const colTasks = tasks.filter(t => t.status_id === status.id);
        const cards = colTasks.length
            ? colTasks.map(task => taskCardHtml(task, loggedIn)).join('')
            : '<div class="kanban-empty">Нет задач</div>';
        return `
        <div class="kanban-column status-${status.id}">
            <div class="kanban-column-header">
                <span>${status.name}</span>
                <span class="kanban-count">${colTasks.length}</span>
            </div>
            <div class="kanban-column-body">${cards}</div>
        </div>`;
    }).join('');
}

// HTML одной карточки задачи (с селектом смены статуса).
function taskCardHtml(task, loggedIn) {
    const options = STATUSES.map(s =>
        `<option value="${s.id}" ${s.id === task.status_id ? 'selected' : ''}>${s.name}</option>`
    ).join('');
    return `
        <div class="task-card status-${task.status_id}">
            <h3 class="task-title">${escapeHtml(task.title)}</h3>
            <p class="task-description">${escapeHtml(task.description || 'Нет описания')}</p>
            <div class="task-meta">
                <span>ID: ${task.id}</span>
                <span>${formatDate(task.created_at)}</span>
            </div>
            <div class="task-control">
                <label>Статус:</label>
                <select class="select task-status-select"
                        onchange="changeStatus(${task.id}, this.value)"
                        ${loggedIn ? '' : 'disabled'}>
                    ${options}
                </select>
            </div>
            ${loggedIn ? `
            <div class="task-actions">
                <button class="btn btn-sm btn-primary" onclick="editTask(${task.id})">Редактировать</button>
                <button class="btn btn-sm btn-danger" onclick="deleteTask(${task.id})">Удалить</button>
            </div>` : ''}
        </div>`;
}

// Смена статуса задачи прямо с карточки (комбо-бокс).
async function changeStatus(taskId, newStatusId) {
    const task = allTasks.find(t => t.id === taskId);
    if (task && task.status_id === parseInt(newStatusId)) return;

    try {
        const response = await fetch(`${API_BASE}/tasks/${taskId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ status_id: parseInt(newStatusId) }),
        });

        if (response.status === 401) { redirectToLogin(); return; }
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка смены статуса');
        }

        showNotification('Статус обновлён');
        loadTasks();
    } catch (error) {
        handleApiError(error);
        loadTasks();  // re-sync the select with the actual server state
    }
}

// Создание задачи
async function createTask(event) {
    event.preventDefault();
    
    if (!window.currentUser) {
        redirectToLogin();
        return;
    }

    const form = event.target;
    const formData = new FormData(form);

    const data = {
        title: formData.get('title'),
        description: formData.get('description') || null,
        creator_id: window.currentUser.id,
        status_id: parseInt(formData.get('status_id'))
    };

    try {
        const response = await fetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin',
            body: JSON.stringify(data)
        });

        if (response.status === 401) { redirectToLogin(); return; }
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка создания задачи');
        }
        
        showNotification('Задача создана успешно!');
        closeCreateTaskModal();
        form.reset();
        loadTasks();
    } catch (error) {
        handleApiError(error);
    }
}

// Редактирование задачи
async function editTask(taskId) {
    const task = allTasks.find(t => t.id === taskId);
    if (!task) return;
    
    document.getElementById('edit-task-id').value = task.id;
    document.getElementById('edit-title').value = task.title;
    document.getElementById('edit-description').value = task.description || '';
    document.getElementById('edit-status_id').value = task.status_id;
    
    showEditTaskModal();
}

// Обновление задачи
async function updateTask(event) {
    event.preventDefault();
    
    const taskId = document.getElementById('edit-task-id').value;
    const form = event.target;
    const formData = new FormData(form);
    
    const data = {
        title: formData.get('title'),
        description: formData.get('description') || null,
        status_id: parseInt(formData.get('status_id'))
    };
    
    try {
        const response = await fetch(`${API_BASE}/tasks/${taskId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin',
            body: JSON.stringify(data)
        });

        if (response.status === 401) { redirectToLogin(); return; }
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка обновления задачи');
        }
        
        showNotification('Задача обновлена успешно!');
        closeEditTaskModal();
        loadTasks();
    } catch (error) {
        handleApiError(error);
    }
}

// Удаление задачи
async function deleteTask(taskId) {
    if (!confirm('Вы уверены, что хотите удалить эту задачу?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/tasks/${taskId}`, {
            method: 'DELETE',
            credentials: 'same-origin'
        });

        if (response.status === 401) { redirectToLogin(); return; }
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка удаления задачи');
        }
        
        showNotification('Задача удалена успешно!');
        loadTasks();
    } catch (error) {
        handleApiError(error);
    }
}

// Модальные окна
function showCreateTaskModal() {
    document.getElementById('create-task-modal').classList.add('show');
}

function closeCreateTaskModal() {
    document.getElementById('create-task-modal').classList.remove('show');
}

function showEditTaskModal() {
    document.getElementById('edit-task-modal').classList.add('show');
}

function closeEditTaskModal() {
    document.getElementById('edit-task-modal').classList.remove('show');
}

// Экранирование HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Поиск
document.getElementById('search')?.addEventListener('keyup', function() {
    loadTasks();
});

// Инициализация
document.addEventListener('DOMContentLoaded', async () => {
    // Wait for the auth state so action buttons render correctly on first paint.
    await loadCurrentUser();
    const createBtn = document.getElementById('create-task-btn');
    if (createBtn && window.currentUser) createBtn.style.display = '';
    loadTasks();
});
