#!/usr/bin/env node
// VASP Agent screenshot — uses system Chrome/Edge headless.
// Usage: node .claude/skills/run-vasp-agent/screenshot.mjs [port]
// Output: /tmp/vasp-agent-shots/

import { execSync } from 'child_process';
import { mkdirSync, existsSync } from 'fs';
import path from 'path';

const PORT = process.env.VASP_PORT || process.argv[2] || 8000;
const BASE = `http://localhost:${PORT}`;
const SHOT_DIR = '/tmp/vasp-agent-shots';

// Find a Chromium-based browser
function findChrome() {
  const candidates = [
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium-browser',
  ];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  return null;
}

function shot(name, seconds = 5) {
  const chrome = findChrome();
  if (!chrome) {
    console.error('No Chrome/Edge found. Install Chrome or set CHROME_PATH.');
    process.exit(1);
  }
  const out = path.join(SHOT_DIR, name);
  // escape quotes for cmd line
  execSync(
    `"${chrome}" --headless=new --disable-gpu --window-size=1280,1400 --screenshot="${out}" --virtual-time-budget=${seconds * 1000} "${BASE}"`,
    { stdio: 'inherit', timeout: 30000 }
  );
  console.log(`  -> ${out}`);
}

mkdirSync(SHOT_DIR, { recursive: true });

console.log(`Screenshots: ${BASE}`);
shot('01-initial.png', 5);
shot('vasp-agent.png', 8);
console.log(`Done. See ${SHOT_DIR}`);
