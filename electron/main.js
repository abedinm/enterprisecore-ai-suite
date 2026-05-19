// Electron main process — launches FastAPI sidecar + loads React app.
const { app, BrowserWindow, Menu, shell, ipcMain, dialog } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const http = require('node:http');

const isDev = process.env.ELECTRON_DEV === '1';
const BACKEND_PORT = Number(process.env.BACKEND_PORT || 8765);
const BACKEND_HOST = '127.0.0.1';
const FRONTEND_DEV_URL = 'http://127.0.0.1:5173';

let mainWindow = null;
let backendProc = null;

function resolveBackendCommand() {
  // In production: bundled PyInstaller exe. In dev: use venv Python.
  if (!isDev) {
    const exe = path.join(process.resourcesPath, 'backend', 'enterprisecore-backend.exe');
    if (fs.existsSync(exe)) return { cmd: exe, args: [], cwd: path.dirname(exe) };
  }
  const venvPython = path.join(__dirname, '..', 'backend', '.venv', 'Scripts', 'python.exe');
  const cwd = path.join(__dirname, '..', 'backend');
  if (fs.existsSync(venvPython)) {
    return { cmd: venvPython, args: ['-m', 'uvicorn', 'app.main:app', '--host', BACKEND_HOST, '--port', String(BACKEND_PORT)], cwd };
  }
  return { cmd: 'python', args: ['-m', 'uvicorn', 'app.main:app', '--host', BACKEND_HOST, '--port', String(BACKEND_PORT)], cwd };
}

function startBackend() {
  const { cmd, args, cwd } = resolveBackendCommand();
  console.log('[backend] starting', cmd, args.join(' '));
  backendProc = spawn(cmd, args, { cwd, env: { ...process.env, PYTHONUNBUFFERED: '1' } });
  backendProc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on('exit', (code) => console.log('[backend] exited', code));
}

function stopBackend() {
  if (backendProc && !backendProc.killed) {
    try { backendProc.kill(); } catch (_) { /* ignore */ }
  }
}

function waitForBackend(timeoutMs = 30000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get({ host: BACKEND_HOST, port: BACKEND_PORT, path: '/api/health', timeout: 1500 }, (res) => {
        if (res.statusCode === 200) return resolve();
        scheduleRetry();
      });
      req.on('error', scheduleRetry);
      req.on('timeout', () => { req.destroy(); scheduleRetry(); });
    };
    const scheduleRetry = () => {
      if (Date.now() - start > timeoutMs) return reject(new Error('Backend did not start in time'));
      setTimeout(attempt, 400);
    };
    attempt();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    backgroundColor: '#0c0f16',
    title: 'EnterpriseCore AI Suite',
    icon: path.join(__dirname, 'resources', 'icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  if (isDev) {
    mainWindow.loadURL(FRONTEND_DEV_URL);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    const indexHtml = path.join(__dirname, '..', 'frontend', 'dist', 'index.html');
    mainWindow.loadFile(indexHtml);
  }

  Menu.setApplicationMenu(buildMenu());
  mainWindow.on('closed', () => { mainWindow = null; });
}

function buildMenu() {
  const template = [
    { label: 'File', submenu: [{ role: 'quit' }] },
    { label: 'Edit', submenu: [{ role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }] },
    { label: 'View', submenu: [{ role: 'reload' }, { role: 'forceReload' }, { type: 'separator' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { type: 'separator' }, { role: 'togglefullscreen' }, { role: 'toggleDevTools' }] },
    { label: 'Help', submenu: [{ label: 'About', click: () => dialog.showMessageBox(mainWindow, { type: 'info', message: 'EnterpriseCore AI Suite', detail: 'Offline business management + AI coding assistant.' }) }] },
  ];
  return Menu.buildFromTemplate(template);
}

ipcMain.handle('app:get-backend-url', () => `http://${BACKEND_HOST}:${BACKEND_PORT}`);

app.whenReady().then(async () => {
  startBackend();
  try {
    await waitForBackend();
  } catch (e) {
    dialog.showErrorBox('Backend failed to start', e.message);
  }
  createWindow();
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', stopBackend);
app.on('activate', () => { if (mainWindow === null) createWindow(); });
