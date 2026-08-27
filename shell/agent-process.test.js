const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { AgentProcessManager, nextBackoffMs } = require('./agent-process');

function makeFakeChild() {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.killCalls = [];
  child.kill = (signal) => child.killCalls.push(signal);
  return child;
}

function makeFakeTimers() {
  const scheduled = [];
  const setTimeoutFn = (fn, delay) => {
    const handle = { fn, delay };
    scheduled.push(handle);
    return handle;
  };
  const clearTimeoutFn = (handle) => {
    const idx = scheduled.indexOf(handle);
    if (idx !== -1) scheduled.splice(idx, 1);
  };
  return {
    setTimeoutFn,
    clearTimeoutFn,
    scheduled,
    fireNext: () => scheduled.shift().fn(),
  };
}

test('nextBackoffMs doubles each attempt and caps at 16000', () => {
  assert.equal(nextBackoffMs(0), 1000);
  assert.equal(nextBackoffMs(1), 2000);
  assert.equal(nextBackoffMs(2), 4000);
  assert.equal(nextBackoffMs(3), 8000);
  assert.equal(nextBackoffMs(4), 16000);
  assert.equal(nextBackoffMs(5), 16000);
});

test('start() spawns python with -m agent.main from the given cwd, hidden window', () => {
  const calls = [];
  const fakeChild = makeFakeChild();
  const spawnFn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    return fakeChild;
  };
  const manager = new AgentProcessManager({ pythonPath: 'C:/py.exe', cwd: 'C:/jarvis', spawnFn });

  manager.start();

  assert.deepEqual(calls, [
    {
      cmd: 'C:/py.exe',
      args: ['-m', 'agent.main'],
      opts: {
        cwd: 'C:/jarvis',
        windowsHide: true,
        env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
      },
    },
  ]);
});

test('start() uses custom args when provided, instead of the default -m agent.main', () => {
  const calls = [];
  const fakeChild = makeFakeChild();
  const spawnFn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    return fakeChild;
  };
  const manager = new AgentProcessManager({
    pythonPath: 'C:/agent.exe', cwd: 'C:/jarvis', args: [], spawnFn,
  });

  manager.start();

  assert.deepEqual(calls[0].args, []);
});

test('start() merges the custom env option on top of the PYTHONUNBUFFERED/PYTHONIOENCODING defaults', () => {
  const calls = [];
  const fakeChild = makeFakeChild();
  const spawnFn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    return fakeChild;
  };
  const manager = new AgentProcessManager({
    pythonPath: 'C:/py.exe', cwd: 'C:/jarvis', spawnFn,
    env: { JARVIS_ENV_PATH: 'C:/Users/x/AppData/Roaming/Jarvis/.env' },
  });

  manager.start();

  assert.equal(calls[0].opts.env.JARVIS_ENV_PATH, 'C:/Users/x/AppData/Roaming/Jarvis/.env');
  assert.equal(calls[0].opts.env.PYTHONUNBUFFERED, '1');
  assert.equal(calls[0].opts.env.PYTHONIOENCODING, 'utf-8');
});

test('start() emits status starting then running on spawn', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });
  const statuses = [];
  manager.on('status', (s) => statuses.push(s));

  manager.start();
  assert.deepEqual(statuses, ['starting']);
  fakeChild.emit('spawn');
  assert.deepEqual(statuses, ['starting', 'running']);
});

test('log lines are buffered with stream origin, split on newlines, empty lines dropped', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });
  const logs = [];
  manager.on('log', (entry) => logs.push(entry));

  manager.start();
  fakeChild.stdout.emit('data', Buffer.from('satir1\nsatir2\n'));
  fakeChild.stderr.emit('data', Buffer.from('hata!\n'));

  assert.deepEqual(logs, [
    { stream: 'status', text: '[AGENT STARTING]' },
    { stream: 'stdout', text: 'satir1' },
    { stream: 'stdout', text: 'satir2' },
    { stream: 'stderr', text: 'hata!' },
  ]);
  assert.deepEqual(manager.getLogHistory(), logs);
});

test('log history is capped at 200 entries (FIFO)', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });

  manager.start();
  for (let i = 0; i < 205; i++) {
    fakeChild.stdout.emit('data', Buffer.from(`line-${i}\n`));
  }

  const history = manager.getLogHistory();
  assert.equal(history.length, 200);
  assert.equal(history[0].text, 'line-5');
  assert.equal(history[199].text, 'line-204');
});

test('unexpected exit schedules a restart with the first backoff delay', () => {
  let spawnCount = 0;
  const spawnFn = () => {
    spawnCount += 1;
    return makeFakeChild();
  };
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });

  manager.start();
  assert.equal(spawnCount, 1);
  manager.child.emit('exit', 1, null);

  assert.equal(timers.scheduled.length, 1);
  assert.equal(timers.scheduled[0].delay, 1000);

  timers.fireNext();
  assert.equal(spawnCount, 2);
});

test('gives up after 5 consecutive fast crashes and emits crashed status, no 6th spawn', () => {
  let spawnCount = 0;
  const spawnFn = () => {
    spawnCount += 1;
    return makeFakeChild();
  };
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });
  const statuses = [];
  manager.on('status', (s) => statuses.push(s));

  manager.start(); // spawn #1
  for (let i = 0; i < 4; i++) {
    manager.child.emit('exit', 1, null);
    timers.fireNext(); // spawns #2..#5
  }
  assert.equal(spawnCount, 5);

  manager.child.emit('exit', 1, null); // 5th crash — give up
  assert.equal(timers.scheduled.length, 0);
  assert.equal(spawnCount, 5);
  assert.ok(statuses.includes('crashed'));
});

test('a crash after STABLE_UPTIME_MS resets the fast-crash counter back to zero', () => {
  let spawnCount = 0;
  const spawnFn = () => {
    spawnCount += 1;
    return makeFakeChild();
  };
  const timers = makeFakeTimers();
  let clock = 0;
  const nowFn = () => clock;
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn, nowFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });

  manager.start(); // spawn #1, startedAt = 0
  for (let i = 0; i < 4; i++) {
    manager.child.emit('exit', 1, null); // clock still 0, fast crash each time
    timers.fireNext();
  }
  assert.equal(spawnCount, 5);

  // 5th process stays alive a long time (>= STABLE_UPTIME_MS) before exiting —
  // this should reset the fast-crash counter instead of tripping 'crashed'
  clock = 20000;
  manager.child.emit('exit', 1, null);

  // counter reset to 0, so this crash schedules attempt-0's backoff (1000ms),
  // not a 'crashed' status
  assert.equal(timers.scheduled.length, 1);
  assert.equal(timers.scheduled[0].delay, 1000);
  timers.fireNext();
  assert.equal(spawnCount, 6);
});

test('stop() kills the child and does not schedule a restart on its exit', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });

  manager.start();
  manager.stop();
  assert.deepEqual(fakeChild.killCalls, ['SIGTERM']);

  fakeChild.emit('exit', 0, 'SIGTERM');
  assert.equal(timers.scheduled.length, 0);
});

test('restart() from a crashed (no child) state respawns immediately without waiting for a timer', () => {
  let spawnCount = 0;
  const spawnFn = () => {
    spawnCount += 1;
    return makeFakeChild();
  };
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });

  manager.start(); // #1
  for (let i = 0; i < 4; i++) {
    manager.child.emit('exit', 1, null);
    timers.fireNext();
  }
  manager.child.emit('exit', 1, null); // gives up, spawnCount == 5, no child
  assert.equal(manager.child, null);

  manager.restart();
  assert.equal(spawnCount, 6);
});

test('restart() while a child is running waits for its real exit before respawning (no race)', () => {
  let spawnCount = 0;
  const children = [];
  const spawnFn = () => {
    spawnCount += 1;
    const child = makeFakeChild();
    children.push(child);
    return child;
  };
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });

  manager.start();
  assert.equal(spawnCount, 1);

  manager.restart();
  assert.equal(spawnCount, 1, 'must not spawn a new child before the old one has actually exited');
  assert.deepEqual(children[0].killCalls, ['SIGTERM']);

  children[0].emit('exit', 0, 'SIGTERM');
  assert.equal(spawnCount, 2);
});

test('restart() completes even if the dying child only emits \'error\', never \'exit\'', () => {
  let spawnCount = 0;
  const children = [];
  const spawnFn = () => {
    spawnCount += 1;
    const child = makeFakeChild();
    children.push(child);
    return child;
  };
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });

  manager.start(); // spawn #1
  manager.restart(); // pending = true, kills #1

  children[0].emit('error', new Error('ENOENT'));
  assert.equal(spawnCount, 2, 'restart must complete via the error path alone, not get stuck');

  // the manager must be usable again afterward — _pendingRestart must not be stuck true
  manager.restart();
  children[1].emit('exit', 0, 'SIGTERM');
  assert.equal(spawnCount, 3);
});

test('a second concurrent restart() call while one is pending is a no-op', () => {
  let spawnCount = 0;
  const children = [];
  const spawnFn = () => {
    spawnCount += 1;
    const child = makeFakeChild();
    children.push(child);
    return child;
  };
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });

  manager.start(); // spawn #1
  manager.restart(); // pending = true, kills #1
  manager.restart(); // must be a no-op — still pending

  assert.equal(spawnCount, 1);
  assert.deepEqual(children[0].killCalls, ['SIGTERM']);

  children[0].emit('exit', 0, 'SIGTERM');
  assert.equal(spawnCount, 2, 'exactly one new spawn from the real exit, not two');
});

test('restart() does not leave a stray scheduled respawn behind (regression)', () => {
  let spawnCount = 0;
  const children = [];
  const spawnFn = () => {
    spawnCount += 1;
    const child = makeFakeChild();
    children.push(child);
    return child;
  };
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });

  manager.start(); // #1
  manager.restart(); // kills #1
  children[0].emit('exit', 0, 'SIGTERM'); // completes the restart -> spawns #2

  assert.equal(spawnCount, 2);
  assert.equal(timers.scheduled.length, 0, 'a successful restart must not also schedule a backoff respawn');
});

test('stop() called while a restart is pending does not spawn a new child', () => {
  let spawnCount = 0;
  const children = [];
  const spawnFn = () => {
    spawnCount += 1;
    const child = makeFakeChild();
    children.push(child);
    return child;
  };
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });

  manager.start(); // #1
  manager.restart(); // kills #1, pending
  manager.stop(); // quits before #1's exit arrives

  children[0].emit('exit', 0, 'SIGTERM'); // #1 finally reports exit

  assert.equal(spawnCount, 1, 'stop() during a pending restart must not let the pending restart spawn a new child');
  assert.equal(timers.scheduled.length, 0);
});

test('an \'error\' event alone triggers the same backoff scheduling as exit, without throwing', () => {
  let spawnCount = 0;
  const spawnFn = () => {
    spawnCount += 1;
    return makeFakeChild();
  };
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });

  manager.start();
  assert.doesNotThrow(() => manager.child.emit('error', new Error('ENOENT')));

  assert.equal(timers.scheduled.length, 1);
  assert.equal(timers.scheduled[0].delay, 1000);
  timers.fireNext();
  assert.equal(spawnCount, 2);
});

test('status transitions are recorded into the same chronological history as log lines', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });

  manager.start();
  fakeChild.stdout.emit('data', Buffer.from('merhaba\n'));
  fakeChild.emit('spawn');

  assert.deepEqual(manager.getLogHistory(), [
    { stream: 'status', text: '[AGENT STARTING]' },
    { stream: 'stdout', text: 'merhaba' },
    { stream: 'status', text: '[AGENT RUNNING]' },
  ]);
});

test('the external status event still fires unchanged for main.js IPC forwarding', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });
  const statuses = [];
  manager.on('status', (s) => statuses.push(s));

  manager.start();
  fakeChild.emit('spawn');

  assert.deepEqual(statuses, ['starting', 'running']);
});
