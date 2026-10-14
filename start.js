const { execSync, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// 1. Setup Backend
console.log('⚙️ Setting up backend...');
const backendDir = path.join(__dirname, 'backend');

// Create virtual environment if it doesn't exist
if (!fs.existsSync(path.join(backendDir, 'venv'))) {
  execSync('python -m venv venv', { cwd: backendDir, stdio: 'inherit' });
}

// Copy .env if it doesn't exist
if (!fs.existsSync(path.join(backendDir, '.env')) && fs.existsSync(path.join(backendDir, '.env.example'))) {
  const copyCmd = process.platform === 'win32' ? 'copy .env.example .env' : 'cp .env.example .env';
  execSync(copyCmd, { cwd: backendDir, stdio: 'inherit' });
}

// Determine python/pip paths based on OS
const isWin = process.platform === 'win32';
const pythonPath = isWin ? path.join(backendDir, 'venv', 'Scripts', 'python.exe') : path.join(backendDir, 'venv', 'bin', 'python');
const pipPath = isWin ? path.join(backendDir, 'venv', 'Scripts', 'pip.exe') : path.join(backendDir, 'venv', 'bin', 'pip');

// Install python dependencies
execSync(`"${pipPath}" install -r requirements.txt`, { cwd: backendDir, stdio: 'inherit' });

// 2. Setup Frontend
console.log('⚙️ Setting up frontend...');
const frontendDir = path.join(__dirname, 'frontend');
execSync('npm install', { cwd: frontendDir, stdio: 'inherit' });

// 3. Start Both Concurrently
console.log('🚀 Starting API and Frontend...');

const api = spawn(`"${pythonPath}"`, ['run.py'], { cwd: backendDir, shell: true, stdio: 'inherit' });
const frontend = spawn('npm', ['run', 'dev'], { cwd: frontendDir, shell: true, stdio: 'inherit' });

// Handle exit cleanly
process.on('SIGINT', () => {
  api.kill();
  frontend.kill();
  process.exit();
});
