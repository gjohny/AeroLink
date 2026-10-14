import { useEffect, useState } from "react";
import { createTask, deleteTask, getHealth, getTasks, updateTask } from "./api";

export default function App() {
  const [status, setStatus] = useState("checking");
  const [tasks, setTasks] = useState([]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getHealth()
      .then(() => setStatus("connected"))
      .catch(() => setStatus("offline"));
    getTasks()
      .then(setTasks)
      .catch((e) => setError(e.message));
  }, []);

  async function handleAdd(e) {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      const task = await createTask(title);
      setTasks([task, ...tasks]);
      setTitle("");
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleToggle(task) {
    try {
      const updated = await updateTask(task.id, { done: !task.done });
      setTasks(tasks.map((t) => (t.id === task.id ? updated : t)));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete(id) {
    try {
      await deleteTask(id);
      setTasks(tasks.filter((t) => t.id !== id));
    } catch (err) {
      setError(err.message);
    }
  }

  const statusText = {
    checking: "Checking connection…",
    connected: "Frontend, backend and database are connected",
    offline: "Backend unreachable. Is Flask running on port 5000?",
  }[status];

  return (
    <main className="app">
      <h1>Tasks</h1>
      <p className={`status status-${status}`}>{statusText}</p>

      <form className="add" onSubmit={handleAdd}>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="What needs doing?"
          aria-label="New task"
        />
        <button type="submit">Add task</button>
      </form>

      {error && <p className="error">{error}</p>}

      {tasks.length === 0 ? (
        <p className="empty">No tasks yet. Add your first one above.</p>
      ) : (
        <ul className="tasks">
          {tasks.map((task) => (
            <li key={task.id} className={task.done ? "done" : ""}>
              <label>
                <input
                  type="checkbox"
                  checked={task.done}
                  onChange={() => handleToggle(task)}
                />
                <span>{task.title}</span>
              </label>
              <button
                className="delete"
                onClick={() => handleDelete(task.id)}
                aria-label={`Delete ${task.title}`}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
