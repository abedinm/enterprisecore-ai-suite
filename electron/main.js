// Electron main process — launches FastAPI sidecar, manages encrypted credential vault,
// and exposes file/dialog IPC for the AI Coding Assistant.
const { app, BrowserWindow, Menu, shell, ipcMain, dialog, safeStorage } = require('electron');
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

// ---- Encrypted credential vault ----------------------------------------
function vaultPath() {
  const dir = path.join(app.getPath('userData'), 'vault');
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, 'credentials.enc');
}

function readVault() {
  const p = vaultPath();
  if (!fs.existsSync(p)) return {};
  const blob = fs.readFileSync(p);
  if (blob.length === 0) return {};
  if (!safeStorage.isEncryptionAvailable()) {
    // Fall back to plaintext JSON file in user data; warn loudly in dev.
    try { return JSON.parse(blob.toString('utf-8')); }
    catch { return {}; }
  }
  try {
    const decrypted = safeStorage.decryptString(blob);
    return JSON.parse(decrypted);
  } catch (e) {
    console.error('[vault] decrypt failed:', e);
    return {};
  }
}

function writeVault(data) {
  const p = vaultPath();
  const payload = JSON.stringify(data);
  if (!safeStorage.isEncryptionAvailable()) {
    fs.writeFileSync(p, payload, { mode: 0o600 });
    return;
  }
  const enc = safeStorage.encryptString(payload);
  fs.writeFileSync(p, enc, { mode: 0o600 });
}

ipcMain.handle('vault:get', (_e, key) => {
  const data = readVault();
  return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null;
});

ipcMain.handle('vault:set', (_e, key, value) => {
  const data = readVault();
  if (value === null || value === undefined || value === '') {
    delete data[key];
  } else {
    data[key] = value;
  }
  writeVault(data);
  return true;
});

ipcMain.handle('vault:list-keys', () => {
  return Object.keys(readVault());
});

ipcMain.handle('vault:clear', () => {
  writeVault({});
  return true;
});

ipcMain.handle('vault:available', () => {
  return { encrypted: safeStorage.isEncryptionAvailable() };
});

// ---- File / directory dialogs ------------------------------------------
ipcMain.handle('dialog:open-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory'],
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

ipcMain.handle('dialog:open-file', async (_e, filters) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: filters || [{ name: 'All files', extensions: ['*'] }],
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

ipcMain.handle('dialog:save-file', async (_e, defaultPath, filters) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath,
    filters: filters || [{ name: 'All files', extensions: ['*'] }],
  });
  if (result.canceled || !result.filePath) return null;
  return result.filePath;
});

ipcMain.handle('app:get-backend-url', () => `http://${BACKEND_HOST}:${BACKEND_PORT}`);
ipcMain.handle('app:platform', () => process.platform);

ipcMain.handle('shell:open-external', (_e, url) => {
  if (typeof url === 'string' && (url.startsWith('http://') || url.startsWith('https://'))) {
    shell.openExternal(url);
    return true;
  }
  return false;
});

// ---- Backend sidecar ---------------------------------------------------
function resolveBackendCommand() {
  if (!isDev) {
    const exe = path.join(process.resourcesPath, 'backend', 'enterprisecore-backend.exe');
    if (fs.existsSync(exe)) return { cmd: exe, args: [], cwd: path.dirname(exe) };
  }
  const venvPython = path.join(__dirname, '..', 'backend', '.venv', 'Scripts', 'python.exe');
  const cwd = path.join(__dirname, '..', 'backend');
  if (fs.existsSync(venvPython)) {
    return {
      cmd: venvPython,
      args: ['-m', 'uvicorn', 'app.main:app', '--host', BACKEND_HOST, '--port', String(BACKEND_PORT)],
      cwd,
    };
  }
  return {
    cmd: 'python',
    args: ['-m', 'uvicorn', 'app.main:app', '--host', BACKEND_HOST, '--port', String(BACKEND_PORT)],
    cwd,
  };
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
      const req = http.get(
        { host: BACKEND_HOST, port: BACKEND_PORT, path: '/api/health', timeout: 1500 },
        (res) => {
          if (res.statusCode === 200) return resolve();
          scheduleRetry();
        },
      );
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

// ---- Window ------------------------------------------------------------
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1480,
    height: 920,
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
    {
      label: 'File',
      submenu: [
        { label: 'Open Project Folder…', accelerator: 'CmdOrCtrl+O',
          click: () => mainWindow?.webContents.send('menu:open-project') },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    { label: 'Edit', submenu: [
      { role: 'undo' }, { role: 'redo' }, { type: 'separator' },
      { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' },
    ] },
    { label: 'View', submenu: [
      { role: 'reload' }, { role: 'forceReload' }, { type: 'separator' },
      { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { type: 'separator' },
      { role: 'togglefullscreen' }, { role: 'toggleDevTools' },
    ] },
    {
      label: 'AI Coding',
      submenu: [
        { label: 'New file', accelerator: 'CmdOrCtrl+N',
          click: () => mainWindow?.webContents.send('menu:new-file') },
        { label: 'Save file', accelerator: 'CmdOrCtrl+S',
          click: () => mainWindow?.webContents.send('menu:save-file') },
        { label: 'Command palette', accelerator: 'CmdOrCtrl+Shift+P',
          click: () => mainWindow?.webContents.send('menu:command-palette') },
      ],
    },
    {
      label: 'Help',
      submenu: [
        { label: 'About', click: () => dialog.showMessageBox(mainWindow, {
          type: 'info',
          message: 'EnterpriseCore AI Suite',
          detail: 'Offline business management + AI coding assistant.\nAPI keys are encrypted locally using OS-level safeStorage.',
        }) },
      ],
    },
  ];
  return Menu.buildFromTemplate(template);
}

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
