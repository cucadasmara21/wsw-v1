#!/usr/bin/env node
// Dev runner (Node 18+ / Node 24 compatible)
//
// Verification checklist (Windows PowerShell):
//   docker compose up -d
//   $env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/wsw_db"
//   python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
//   (cd frontend; npm run dev -- --host 127.0.0.1 --port 5173)
//   curl.exe -i http://127.0.0.1:8000/api/universe/v8/health   # expects postgresql + v8_ready=true
//   curl.exe -I "http://127.0.0.1:8000/api/universe/v8/snapshot?format=vertex28&compression=zstd"  # 200/204
//
// Notes:
// - Legacy endpoints can run on SQLite. TITAN V8 requires PostgreSQL (DATABASE_URL must be postgresql://...).
// - This script fails fast if ports 8000/5173 are already in use.

const net = require('net');
const concurrently = require('concurrently');

const DEFAULT_POSTGRES_DSN = 'postgresql://postgres:postgres@127.0.0.1:5432/wsw_db';

async function isPortInUse(host, port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    const onDone = (inUse) => {
      try { socket.destroy(); } catch {}
      resolve(inUse);
    };

    socket.setTimeout(400);
    socket.once('connect', () => onDone(true));
    socket.once('timeout', () => onDone(false));
    socket.once('error', () => onDone(false));
    socket.connect(port, host);
  });
}

async function main() {
  const host = '127.0.0.1';
  const backendPort = 8000;
  const frontendPort = 5173;

  const backendBusy = await isPortInUse(host, backendPort);
  if (backendBusy) {
    console.error(`[dev] Port ${backendPort} is already in use on ${host}. Stop the existing backend, or change ports.`);
    process.exit(1);
  }

  const frontendBusy = await isPortInUse(host, frontendPort);
  if (frontendBusy) {
    console.error(`[dev] Port ${frontendPort} is already in use on ${host}. Stop the existing frontend, or change ports.`);
    process.exit(1);
  }

  // Ensure backend uses PostgreSQL for Titan V8 (legacy endpoints can still run on SQLite).
  // We intentionally set DATABASE_URL for the backend process started by this dev runner.
  const backend =
    process.platform === 'win32'
      ? `powershell -NoProfile -Command "$env:DATABASE_URL='${DEFAULT_POSTGRES_DSN}'; $env:DATABASE_DSN_ASYNC='${DEFAULT_POSTGRES_DSN}'; python -m uvicorn main:app --host ${host} --port ${backendPort} --reload"`
      : `DATABASE_URL='${DEFAULT_POSTGRES_DSN}' DATABASE_DSN_ASYNC='${DEFAULT_POSTGRES_DSN}' python -m uvicorn main:app --host ${host} --port ${backendPort} --reload`;
  const frontend = `cd frontend && npm run dev -- --host ${host} --port ${frontendPort}`;

  const run = concurrently(
    [
      { command: backend, name: 'backend', prefixColor: 'blue' },
      { command: frontend, name: 'frontend', prefixColor: 'green' },
    ],
    {
      killOthers: ['failure', 'success'],
      restartTries: 0,
      raw: false,
    }
  );

  // concurrently v7 returns { result: Promise<...>, commands: [...] }
  const resultPromise = run && run.result ? run.result : run;
  await resultPromise;
}

main().then(
  () => process.exit(0),
  (err) => {
    console.error('Error running dev runner', err);
    process.exit(1);
  }
);
