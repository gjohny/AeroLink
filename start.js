const { execSync, execFileSync, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

// 1. Setup Backend
console.log('⚙️ Setting up backend...');
const backendDir = path.join(__dirname, 'backend');
const isWin = process.platform === 'win32';
const pythonCandidates = process.env.AEROLINK_PYTHON
  ? [process.env.AEROLINK_PYTHON]
  : ['python3.12', 'python3.13', 'python3.11', 'python3.10', 'python3', 'python'];
const pythonCommand = pythonCandidates.find((candidate) => {
  try {
    execFileSync(candidate, ['-c', 'import sys, hashlib; raise SystemExit(sys.version_info < (3, 10) or not hasattr(hashlib, "scrypt"))'], { stdio: 'ignore' });
    return true;
  } catch { return false; }
});
if (!pythonCommand) throw new Error('Python 3.10+ with scrypt support is required. Set AEROLINK_PYTHON to its executable path.');

// Create virtual environment if it doesn't exist
if (!fs.existsSync(path.join(backendDir, 'venv'))) {
  execFileSync(pythonCommand, ['-m', 'venv', 'venv'], { cwd: backendDir, stdio: 'inherit' });
}

// Copy .env if it doesn't exist
if (!fs.existsSync(path.join(backendDir, '.env')) && fs.existsSync(path.join(backendDir, '.env.example'))) {
  const copyCmd = process.platform === 'win32' ? 'copy .env.example .env' : 'cp .env.example .env';
  execSync(copyCmd, { cwd: backendDir, stdio: 'inherit' });
}

// Supply a persistent development session key when setting up a fresh checkout.
const envPath = path.join(backendDir, '.env');
if (!process.env.SECRET_KEY && (!fs.existsSync(envPath) || !/^SECRET_KEY=.+/m.test(fs.readFileSync(envPath, 'utf8')))) {
  fs.appendFileSync(envPath, `\nSECRET_KEY=${crypto.randomBytes(32).toString('hex')}\n`);
}

// Determine python/pip paths based on OS
const pythonPath = isWin ? path.join(backendDir, 'venv', 'Scripts', 'python.exe') : path.join(backendDir, 'venv', 'bin', 'python');
const pipPath = isWin ? path.join(backendDir, 'venv', 'Scripts', 'pip.exe') : path.join(backendDir, 'venv', 'bin', 'pip');

try {
  execFileSync(pythonPath, ['-c', 'import sys, hashlib; raise SystemExit(sys.version_info < (3, 10) or not hasattr(hashlib, "scrypt"))'], { stdio: 'ignore' });
} catch {
  throw new Error('backend/venv needs Python 3.10+ with scrypt. Recreate the virtual environment using a supported Python.');
}

// Install python dependencies
execSync(`"${pipPath}" install -r requirements.txt`, { cwd: backendDir, stdio: 'inherit' });

// 2. Setup Frontend
console.log('⚙️ Setting up frontend...');
const frontendDir = path.join(__dirname, 'frontend');
execSync('npm install', { cwd: frontendDir, stdio: 'inherit' });

// Initialize additive tables before starting API/worker concurrently.
execSync(`"${pythonPath}" -c "from app import create_app; create_app()"`, { cwd: backendDir, stdio: 'inherit' });

// 3. Start Both Concurrently
console.log('🚀 Starting API and Frontend...');

const api = spawn(pythonPath, ['run.py'], { cwd: backendDir, stdio: 'inherit' });
const weatherWorker = spawn(pythonPath, ['-m', 'flask', '--app', 'run:app', 'weather-worker'], { cwd: backendDir, stdio: 'inherit' });
const frontend = spawn('npm', ['run', 'dev'], { cwd: frontendDir, shell: true, stdio: 'inherit' });

// Handle exit cleanly
function shutdown() {
  api.kill();
  frontend.kill();
  weatherWorker.kill();
  process.exit();
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
