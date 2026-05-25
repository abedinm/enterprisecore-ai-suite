// Electron main process — launches FastAPI sidecar, manages encrypted credential vault,
// and exposes file/dialog IPC for the AI Coding Assistant.
const { app, BrowserWindow, Menu, shell, ipcMain, dialog, safeStorage } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { spawn, execSync } = require('node:child_process');
const http = require('node:http');
const { autoUpdater } = require('electron-updater');

const isDev = process.env.ELECTRON_DEV === '1';
const BACKEND_HOST = '127.0.0.1';
const FRONTEND_DEV_URL = 'http://127.0.0.1:5173';
const BACKEND_PORT = Number(process.env.BACKEND_PORT || 8765);

let mainWindow = null;
let backendProc = null;

const net = require('node:net');
function isPortInUse(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once('error', () => resolve(true));
    server.listen(port, BACKEND_HOST, () => server.close(() => resolve(false)));
  });
}

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
  const uvicornArgs = ['-m', 'uvicorn', 'app.main:app', '--host', BACKEND_HOST, '--port', String(BACKEND_PORT)];
  if (fs.existsSync(venvPython)) return { cmd: venvPython, args: uvicornArgs, cwd };
  return { cmd: 'python', args: uvicornArgs, cwd };
}

// ---- Backend lifecycle (robust against Windows process-leak quirks) ----

// Probe whether the listener on BACKEND_PORT is OUR backend (vs a foreign app
// like Holy Grail's aurora-backend that defaults to the same port).
function probeIsOurBackend() {
  return new Promise((resolve) => {
    const req = http.get(
      { host: BACKEND_HOST, port: BACKEND_PORT, path: '/api/health', timeout: 1500 },
      (res) => {
        let body = '';
        res.on('data', (c) => (body += c));
        res.on('end', () => {
          if (res.statusCode !== 200) return resolve(false);
          try {
            const j = JSON.parse(body);
            // Our backend's /api/health responds with at least a status ok.
            // Holy Grail's /health responds at /health (no /api prefix), so a
            // 200 here is a strong signal we hit our app.
            resolve(typeof j === 'object' && j !== null);
          } catch { resolve(false); }
        });
      },
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

// Kill any leftover enterprisecore-backend.exe on Windows (catches orphans
// from a previous launch where Electron crashed before stopBackend ran, or
// where the PyInstaller child process outlived its bootstrapper).
function killOrphanBackends() {
  if (process.platform !== 'win32') return;
  try {
    execSync('taskkill /F /IM enterprisecore-backend.exe', { stdio: 'ignore' });
  } catch (_) { /* none running — fine */ }
}

// Tree-kill on Windows: kills the spawned process AND any children it spawned
// (PyInstaller bootstraps a child interpreter that doesn't die with the parent).
function killProcessTree(pid) {
  if (!pid) return;
  if (process.platform === 'win32') {
    try { execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' }); } catch (_) { /* ignore */ }
  } else {
    try { process.kill(pid, 'SIGKILL'); } catch (_) { /* ignore */ }
  }
}

async function startBackend() {
  if (await isPortInUse(BACKEND_PORT)) {
    // Case 1: it's our own backend from a prior run that didn't clean up.
    if (await probeIsOurBackend()) {
      console.log('[backend] reusing existing EnterpriseCore backend on', BACKEND_PORT);
      return; // The Electron renderer will talk to it just fine.
    }
    // Case 2: orphan EC backend that doesn't respond (mid-shutdown). Kill any
    // by-name and wait a moment for Windows to release the socket.
    killOrphanBackends();
    await new Promise((r) => setTimeout(r, 1500));
    if (await isPortInUse(BACKEND_PORT)) {
      // Case 3: a genuinely foreign app holds the port. Tell the user.
      dialog.showErrorBox(
        'EnterpriseCore — port in use',
        `Port ${BACKEND_PORT} is held by another application that isn't EnterpriseCore.\n\n` +
        'Stop the other app (Holy Grail, another web server) or set BACKEND_PORT to a free port ' +
        'before launching EnterpriseCore AI Suite.',
      );
      app.quit();
      return;
    }
  }
  const { cmd, args, cwd } = resolveBackendCommand();
  console.log('[backend] starting on port', BACKEND_PORT, cmd, args.join(' '));
  backendProc = spawn(cmd, args, {
    cwd,
    env: { ...process.env, PYTHONUNBUFFERED: '1', BACKEND_PORT: String(BACKEND_PORT), BACKEND_HOST },
    windowsHide: true,
  });
  backendProc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on('exit', (code) => console.log('[backend] exited', code));
}

function stopBackend() {
  if (backendProc && !backendProc.killed) {
    const pid = backendProc.pid;
    try { backendProc.kill(); } catch (_) { /* ignore */ }
    // Hard-kill the entire tree on Windows — PyInstaller's child interpreter
    // doesn't die when the bootstrapper dies, so it leaks port 8765 otherwise.
    if (pid) killProcessTree(pid);
  }
  // Belt-and-suspenders: sweep any by-name orphans we didn't track.
  killOrphanBackends();
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
    const packagedIndex = path.join(process.resourcesPath, 'frontend', 'index.html');
    const devIndex = path.join(__dirname, '..', 'frontend', 'dist', 'index.html');
    const indexHtml = fs.existsSync(packagedIndex) ? packagedIndex : devIndex;
    mainWindow.loadFile(indexHtml);
    // TEMP DEBUG: surface renderer errors in packaged build.
    mainWindow.webContents.openDevTools({ mode: 'right' });
  }

  // Log every renderer-side failure to the Electron main-process stdout so
  // we can see what's broken without the user opening DevTools.
  mainWindow.webContents.on('did-fail-load', (_e, code, desc, url) => {
    console.error('[renderer] did-fail-load', code, desc, url);
  });
  mainWindow.webContents.on('render-process-gone', (_e, details) => {
    console.error('[renderer] render-process-gone', details);
  });
  mainWindow.webContents.on('console-message', (_e, level, message, line, sourceId) => {
    console.log(`[renderer:console:${level}] ${message}  (${sourceId}:${line})`);
  });

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

// ---- Auto-updater ------------------------------------------------------
// Wires electron-updater to check for new releases on startup + every 4h.
// No-ops in dev or when EC_UPDATE_CHANNEL=disabled is set. Failures (DNS,
// 404 on the update URL) are swallowed so the user never sees an error.
function setupAutoUpdater() {
  // Skip in dev — auto-updater hits real release URLs and would spam logs.
  if (isDev) return;
  // Explicit opt-out for ops / air-gapped installs.
  if (process.env.EC_UPDATE_CHANNEL === 'disabled') return;
  // Skip if no publish URL configured (signal of "don't try").
  if (!process.env.EC_UPDATE_CHANNEL && !app.isPackaged) return;

  autoUpdater.logger = console;
  autoUpdater.autoDownload = false;       // prompt before downloading
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.allowPrerelease = process.env.EC_UPDATE_CHANNEL === 'beta';

  autoUpdater.on('error', (err) => console.error('[updater]', err));
  autoUpdater.on('update-available', (info) => {
    console.log('[updater] update available:', info.version);
    if (!mainWindow) return;
    dialog.showMessageBox(mainWindow, {
      type: 'info',
      buttons: ['Download', 'Skip'],
      defaultId: 0,
      title: 'Update available',
      message: `EnterpriseCore ${info.version} is available.`,
      detail: 'Download now? The update will install when you next quit the app.',
    }).then(({ response }) => {
      if (response === 0) autoUpdater.downloadUpdate();
    });
  });
  autoUpdater.on('update-downloaded', () => {
    if (!mainWindow) return;
    dialog.showMessageBox(mainWindow, {
      type: 'info',
      buttons: ['Restart now', 'Later'],
      defaultId: 0,
      title: 'Update ready',
      message: 'Update downloaded — restart EnterpriseCore to apply.',
    }).then(({ response }) => {
      if (response === 0) autoUpdater.quitAndInstall();
    });
  });

  // Check on startup + every 4 hours.
  autoUpdater.checkForUpdatesAndNotify().catch(() => {});
  setInterval(() => autoUpdater.checkForUpdatesAndNotify().catch(() => {}), 4 * 60 * 60 * 1000);
}

// Manual trigger from the renderer (e.g. Help → Check for updates).
ipcMain.handle('app:check-for-updates', async () => {
  if (isDev) return { status: 'skipped', reason: 'dev' };
  if (process.env.EC_UPDATE_CHANNEL === 'disabled') return { status: 'skipped', reason: 'disabled' };
  try {
    const result = await autoUpdater.checkForUpdates();
    return {
      status: 'checked',
      updateAvailable: !!(result && result.updateInfo && result.updateInfo.version
        && result.updateInfo.version !== app.getVersion()),
      version: result && result.updateInfo ? result.updateInfo.version : null,
    };
  } catch (err) {
    return { status: 'error', error: String(err && err.message || err) };
  }
});

app.whenReady().then(async () => {
  startBackend();
  try {
    await waitForBackend();
  } catch (e) {
    dialog.showErrorBox('Backend failed to start', e.message);
  }
  createWindow();
  setupAutoUpdater();
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', stopBackend);
app.on('activate', () => { if (mainWindow === null) createWindow(); });
