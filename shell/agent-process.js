const { EventEmitter } = require('node:events');
const { spawn } = require('node:child_process');

const MAX_BACKOFF_MS = 16000;
const MAX_RESTART_ATTEMPTS = 5;
const STABLE_UPTIME_MS = 10000;
const LOG_HISTORY_LIMIT = 200;

function nextBackoffMs(attempt) {
  return Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS);
}

class AgentProcessManager extends EventEmitter {
  constructor({ pythonPath, cwd, args = ['-m', 'agent.main'], env = {}, spawnFn = spawn, setTimeoutFn = setTimeout, clearTimeoutFn = clearTimeout, nowFn = Date.now }) {
    super();
    this.pythonPath = pythonPath;
    this.cwd = cwd;
    this.args = args;
    this.env = env;
    this.spawnFn = spawnFn;
    this.setTimeoutFn = setTimeoutFn;
    this.clearTimeoutFn = clearTimeoutFn;
    this.nowFn = nowFn;

    this.child = null;
    this.logHistory = [];
    this.consecutiveFastCrashes = 0;
    this.startedAt = null;
    this._intentionalStop = false;
    this._restartTimer = null;
    this._pendingRestart = false;
  }

  start() {
    this._intentionalStop = false;
    this._emitStatus('starting');

    const child = this.spawnFn(this.pythonPath, this.args, {
      cwd: this.cwd,
      windowsHide: true,
      env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', ...this.env },
    });
    this.child = child;
    this.startedAt = this.nowFn();

    let handled = false;
    const handleFailure = () => {
      if (handled) return;
      handled = true;
      this._handleExit(child);
    };

    child.stdout.on('data', (chunk) => this._pushLog('stdout', chunk));
    child.stderr.on('data', (chunk) => this._pushLog('stderr', chunk));
    child.on('spawn', () => this._emitStatus('running'));
    child.on('exit', handleFailure);
    child.on('error', (err) => {
      this._pushLog('stderr', Buffer.from(`spawn error: ${err.message}\n`));
      handleFailure();
    });
  }

  stop() {
    this._intentionalStop = true;
    this._pendingRestart = false;
    this.removeAllListeners('_childDown');
    if (this._restartTimer) {
      this.clearTimeoutFn(this._restartTimer);
      this._restartTimer = null;
    }
    if (this.child) {
      // Sadece SIGTERM: Windows'ta her sinyal TerminateProcess'e eşlenir ve
      // her zaman başarılı olur, bu yüzden SIGKILL'e yükseltmeye gerek yok.
      this.child.kill('SIGTERM');
    }
  }

  restart() {
    this.consecutiveFastCrashes = 0;
    if (this._restartTimer) {
      this.clearTimeoutFn(this._restartTimer);
      this._restartTimer = null;
    }

    if (this._pendingRestart) return;

    if (this.child) {
      this._pendingRestart = true;
      this._intentionalStop = true;
      this.once('_childDown', () => {
        this._pendingRestart = false;
        this.start();
      });
      this.child.kill('SIGTERM');
    } else {
      this.start();
    }
  }

  getLogHistory() {
    return this.logHistory.slice();
  }

  _handleExit(child) {
    if (this.child !== child) return;
    this.child = null;
    const wasIntentional = this._intentionalStop;
    this.emit('_childDown');
    if (wasIntentional) return;

    const uptime = this.nowFn() - this.startedAt;
    if (uptime >= STABLE_UPTIME_MS) {
      this.consecutiveFastCrashes = 0;
    } else {
      this.consecutiveFastCrashes += 1;
    }

    if (this.consecutiveFastCrashes >= MAX_RESTART_ATTEMPTS) {
      this._emitStatus('crashed');
      return;
    }

    const delay = nextBackoffMs(Math.max(this.consecutiveFastCrashes - 1, 0));
    this._emitStatus('restarting');
    this._restartTimer = this.setTimeoutFn(() => this.start(), delay);
  }

  _emitStatus(status) {
    this._recordHistory({ stream: 'status', text: `[AGENT ${status.toUpperCase()}]` });
    this.emit('status', status);
  }

  _recordHistory(entry) {
    this.logHistory.push(entry);
    if (this.logHistory.length > LOG_HISTORY_LIMIT) this.logHistory.shift();
    this.emit('log', entry);
  }

  _pushLog(stream, chunk) {
    const text = chunk.toString('utf-8');
    for (const line of text.split(/\r?\n/)) {
      if (!line) continue;
      this._recordHistory({ stream, text: line });
    }
  }
}

module.exports = { AgentProcessManager, nextBackoffMs };
