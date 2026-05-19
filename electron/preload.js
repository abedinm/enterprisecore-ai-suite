// Preload — exposes a tightly-scoped API to the renderer.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('enterpriseCore', {
  isDesktop: true,
  platform: process.platform,
  getBackendUrl: () => ipcRenderer.invoke('app:get-backend-url'),
  getPlatform: () => ipcRenderer.invoke('app:platform'),

  vault: {
    get: (key) => ipcRenderer.invoke('vault:get', String(key)),
    set: (key, value) => ipcRenderer.invoke('vault:set', String(key), value),
    listKeys: () => ipcRenderer.invoke('vault:list-keys'),
    clear: () => ipcRenderer.invoke('vault:clear'),
    available: () => ipcRenderer.invoke('vault:available'),
  },

  dialog: {
    openDirectory: () => ipcRenderer.invoke('dialog:open-directory'),
    openFile: (filters) => ipcRenderer.invoke('dialog:open-file', filters),
    saveFile: (defaultPath, filters) => ipcRenderer.invoke('dialog:save-file', defaultPath, filters),
  },

  shell: {
    openExternal: (url) => ipcRenderer.invoke('shell:open-external', url),
  },

  // Menu events -> render-side handlers
  on: (channel, listener) => {
    const allowed = new Set([
      'menu:open-project', 'menu:new-file', 'menu:save-file', 'menu:command-palette',
    ]);
    if (!allowed.has(channel)) return () => {};
    const wrapped = (_e, ...args) => listener(...args);
    ipcRenderer.on(channel, wrapped);
    return () => ipcRenderer.removeListener(channel, wrapped);
  },
});
