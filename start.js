
const { execSync, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const isWin = process.platform === "win32";

// 1. Setup Backend
console.log("⚙️ Setting up backend...");

const backendDir = path.join(__dirname, "backend");

// Create virtual environment if it doesn't exist
if (!fs.existsSync(path.join(backendDir, "venv"))) {
  execSync(
    isWin ? "py -m venv venv" : "python3 -m venv venv",
    { cwd: backendDir, stdio: "inherit" }
  );
}

// Copy .env if it doesn't exist
const envPath = path.join(backendDir, ".env");
const examplePath = path.join(backendDir, ".env.example");

if (!fs.existsSync(envPath) && fs.existsSync(examplePath)) {
  fs.copyFileSync(examplePath, envPath);
}

// Determine Python executable
const pythonPath = isWin
  ? path.join(backendDir, "venv", "Scripts", "python.exe")
  : path.join(backendDir, "venv", "bin", "python");

// Install Python dependencies
execSync(
  `"${pythonPath}" -m pip install -r requirements.txt`,
  { cwd: backendDir, stdio: "inherit" }
);

// 2. Setup Frontend
console.log("⚙️ Setting up frontend...");

const frontendDir = path.join(__dirname, "frontend");

execSync("npm install", {
  cwd: frontendDir,
  stdio: "inherit",
});

// 3. Start Backend and Frontend
console.log("🚀 Starting API and Frontend...");
console.log("Backend: http://127.0.0.1:5001");

const api = spawn(
  pythonPath,
  [
    "-m",
    "flask",
    "--app",
    "app",
    "run",
    "--debug",
    "--port",
    "5001",
  ],
  {
    cwd: backendDir,
    stdio: "inherit",
    shell: false,
  }
);

const frontend = spawn(
  isWin ? "npm.cmd" : "npm",
  ["run", "dev"],
  {
    cwd: frontendDir,
    stdio: "inherit",
    shell: false,
  }
);

// 4. Handle shutdown
let shuttingDown = false;

function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;

  console.log("\nStopping AeroLink servers...");

  api.kill("SIGTERM");
  frontend.kill("SIGTERM");

  setTimeout(() => process.exit(0), 1000);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

api.on("error", (error) => {
  console.error("Backend failed to start:", error.message);
  shutdown();
});

frontend.on("error", (error) => {
  console.error("Frontend failed to start:", error.message);
  shutdown();
});
