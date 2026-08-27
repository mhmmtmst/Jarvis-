const { app, BrowserWindow, ipcMain, session } = require('electron');
const path = require('path');
const fs = require('fs');
const { AgentProcessManager } = require('./agent-process');
const { readSettings, writeSettings, resolveEnvPath } = require('./settings');

let mainWindow = null;

const PROJECT_ROOT = path.join(__dirname, '..');

const ENV_PATH = resolveEnvPath({
  isPackaged: app.isPackaged,
  userDataPath: app.getPath('userData'),
  projectRoot: PROJECT_ROOT,
});

if (app.isPackaged && !fs.existsSync(ENV_PATH)) {
  fs.mkdirSync(path.dirname(ENV_PATH), { recursive: true });
  fs.copyFileSync(path.join(process.resourcesPath, 'agent', '.env.example'), ENV_PATH);
}

const agentManager = new AgentProcessManager({
  pythonPath: app.isPackaged
    ? path.join(process.resourcesPath, 'agent', 'agent.exe')
    : path.join(PROJECT_ROOT, 'agent', 'venv', 'Scripts', 'python.exe'),
  args: app.isPackaged ? [] : ['-m', 'agent.main'],
  cwd: app.isPackaged ? path.join(process.resourcesPath, 'agent') : PROJECT_ROOT,
  env: { JARVIS_ENV_PATH: ENV_PATH },
});

function createWindow() {
  mainWindow = new BrowserWindow({
    fullscreen: true,
    autoHideMenuBar: true,
    backgroundColor: '#05080a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
  return mainWindow;
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    callback(permission === 'media' || permission === 'geolocation');
  });

  createWindow();

  agentManager.on('log', (entry) => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('agent-log', entry);
  });
  agentManager.on('status', (status) => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('agent-status', status);
  });
  agentManager.start();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  agentManager.stop();
});

ipcMain.on('jarvis:quit', () => {
  app.quit();
});

ipcMain.handle('jarvis:restart-agent', () => {
  agentManager.restart();
});

ipcMain.handle('jarvis:agent-log-history', () => agentManager.getLogHistory());

ipcMain.handle('jarvis:get-settings', () => readSettings(ENV_PATH));

ipcMain.handle('jarvis:save-settings', (_event, updates) => {
  writeSettings(ENV_PATH, updates);
  agentManager.restart();
});

ipcMain.handle('jarvis:get-launch-on-startup', () => app.getLoginItemSettings().openAtLogin);

ipcMain.handle('jarvis:set-launch-on-startup', (_event, value) => {
  app.setLoginItemSettings({ openAtLogin: Boolean(value) });
});
