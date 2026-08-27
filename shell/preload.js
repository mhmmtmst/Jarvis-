const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvisShell', {
  quit: () => ipcRenderer.send('jarvis:quit'),
  onAgentLog: (callback) => {
    ipcRenderer.on('agent-log', (_event, entry) => callback(entry));
  },
  onAgentStatus: (callback) => {
    ipcRenderer.on('agent-status', (_event, status) => callback(status));
  },
  getAgentLogHistory: () => ipcRenderer.invoke('jarvis:agent-log-history'),
  restartAgent: () => ipcRenderer.invoke('jarvis:restart-agent'),
  getSettings: () => ipcRenderer.invoke('jarvis:get-settings'),
  saveSettings: (values) => ipcRenderer.invoke('jarvis:save-settings', values),
  getLaunchOnStartup: () => ipcRenderer.invoke('jarvis:get-launch-on-startup'),
  setLaunchOnStartup: (value) => ipcRenderer.invoke('jarvis:set-launch-on-startup', value),
  getAppVersion: () => ipcRenderer.invoke('jarvis:get-app-version'),
  onUpdateStatus: (callback) => {
    ipcRenderer.on('update-status', (_event, status) => callback(status));
  },
});
