// Управление задачами

let allTasks = [];

// Загрузка задач
async function loadTasks() {
    try {
        const statusFilter = document.getElementById('status-filter')?.value;
        const searchQuery = document.getElementById('search')?.value.toLowerCase();
        
        const response = await fetch(`${API_BASE}/tasks`);
        if (!response.ok) throw new Error('Ошибка загрузки задач');
        
        const data = await response.json();
        allTasks = data.tasks || [];
        
        // Фильтрация
        let filteredTasks = allTasks;
        
        if (statusFilter) {
            filteredTasks = filteredTasks.filter(t => t.status_id == statusFilter);
        }
        
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

// Отображение задач
function displayTasks(tasks) {
    const container = document.getElementById('tasks-container');
    
    if (tasks.length === 0) {
        container.innerHTML = '<div class="loading">Задачи не найдены</div>';
        return;
    }
    
    container.innerHTML = tasks.map(task => `
        <div class="task-card status-${task.status_id}">
            <h3 class="task-title">${escapeHtml(task.title)}</h3>
            <p class="task-description">${escapeHtml(task.description || 'Нет описания')}</p>
            <div class="task-meta">
                <span>ID: ${task.id}</span>
                <span>Автор: ${task.creator_id}</span>
            </div>
            <div class="task-meta">
                <span class="task-status status-${task.status_id}">
                    ${getStatusName(task.status_id)}
                </span>
                <span>${formatDate(task.created_at)}</span>
            </div>
            ${window.currentUser ? `
            <div class="task-actions">
                <button class="btn btn-sm btn-primary" onclick="editTask(${task.id})">Редактировать</button>
                <button class="btn btn-sm btn-danger" onclick="deleteTask(${task.id})">Удалить</button>
            </div>` : ''}
        </div>
    `).join('');
}

// Получить название статуса
function getStatusName(statusId) {
    const statuses = {
        1: 'Новая',
        2: 'В работе',
        3: 'Завершена'
    };
    return statuses[statusId] || 'Неизвестно';
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
