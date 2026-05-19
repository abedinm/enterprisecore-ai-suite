const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('enterpriseCore', {
  isDesktop: true,
  platform: process.platform,
  getBackendUrl: () => ipcRenderer.invoke('app:get-backend-url'),
});
