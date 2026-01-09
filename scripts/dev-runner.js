#!/usr/bin/env node
// Lightweight dev runner that uses concurrently & wait-on
// Cross-platform: spawn frontend and backend with the configured scripts

const concurrently = require('concurrently');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const backend = 'python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload';
const frontend = 'cd frontend && npm ci && npm run dev -- --host 0.0.0.0 --port 5173';

concurrently([
  { command: backend, name: 'backend', prefixColor: 'blue' },
  { command: frontend, name: 'frontend', prefixColor: 'green' }
], {
  killOthers: ['failure', 'success'],
  restartTries: 0,
  raw: false
}).then(() => process.exit(0)).catch(err => {
  console.error('Error running dev runner', err);
  process.exit(1);
});
