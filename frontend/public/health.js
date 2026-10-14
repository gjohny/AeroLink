const statusElement = document.querySelector("#status");
const errorElement = document.querySelector("#error");
const emptyElement = document.querySelector("#empty");
const tasksElement = document.querySelector("#tasks");
const formElement = document.querySelector("#add-form");
const titleElement = document.querySelector("#task-title");
let currentTasks = [];

async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let body = {};
    try {
      body = await response.json();
    } catch {
      // The response may not contain a JSON error body.
    }
    throw new Error(body.error || `Request failed (${response.status})`);
  }

  return response.status === 204 ? null : response.json();
}

function showError(error) {
  errorElement.textContent = error.message;
  errorElement.hidden = false;
}

function renderTasks(tasks) {
  tasksElement.replaceChildren();
  emptyElement.hidden = tasks.length > 0;
  if (tasks.length === 0) {
    emptyElement.textContent = "No tasks yet. Add your first one above.";
    return;
  }

  for (const task of tasks) {
    const item = document.createElement("li");
    if (task.done) item.classList.add("done");

    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = task.done;
    checkbox.addEventListener("change", async () => {
      try {
        const updated = await request(`/tasks/${task.id}`, {
          method: "PATCH",
          body: JSON.stringify({ done: checkbox.checked }),
        });
        task.done = updated.done;
        item.classList.toggle("done", task.done);
      } catch (error) {
        checkbox.checked = task.done;
        showError(error);
      }
    });

    const title = document.createElement("span");
    title.textContent = task.title;
    label.append(checkbox, title);

    const deleteButton = document.createElement("button");
    deleteButton.className = "delete";
    deleteButton.textContent = "Delete";
    deleteButton.setAttribute("aria-label", `Delete ${task.title}`);
    deleteButton.addEventListener("click", async () => {
      try {
        await request(`/tasks/${task.id}`, { method: "DELETE" });
        currentTasks = currentTasks.filter(
          (currentTask) => currentTask.id !== task.id
        );
        renderTasks(currentTasks);
      } catch (error) {
        showError(error);
      }
    });

    item.append(label, deleteButton);
    tasksElement.append(item);
  }
}

formElement.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = titleElement.value.trim();
  if (!title) return;

  try {
    const task = await request("/tasks", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
    currentTasks = [task, ...currentTasks];
    renderTasks(currentTasks);
    titleElement.value = "";
    errorElement.hidden = true;
  } catch (error) {
    showError(error);
  }
});

try {
  await request("/health");
  statusElement.textContent = "Frontend, backend and database are connected";
  statusElement.classList.add("status-connected");
} catch {
  statusElement.textContent = "Backend unreachable. Is Flask running on port 5000?";
  statusElement.classList.add("status-offline");
}

try {
  currentTasks = await request("/tasks");
  renderTasks(currentTasks);
} catch (error) {
  emptyElement.hidden = true;
  showError(error);
}
