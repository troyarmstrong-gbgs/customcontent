require('dotenv').config();
const express  = require('express');
const fs       = require('fs');
const path     = require('path');
const cors     = require('cors');

const app  = express();
const PORT = process.env.PORT || 3000;
const DATA = path.join(__dirname, 'data', 'submissions.json');

// ── Middleware ──────────────────────────────────────────────
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ── Storage ─────────────────────────────────────────────────
function load() {
  fs.mkdirSync(path.dirname(DATA), { recursive: true }); // create data/ if missing
  if (!fs.existsSync(DATA)) fs.writeFileSync(DATA, '[]');
  try { return JSON.parse(fs.readFileSync(DATA, 'utf8')); } catch { return []; }
}
function save(d) { fs.writeFileSync(DATA, JSON.stringify(d, null, 2)); }

// ── Google Chat Notification ────────────────────────────────
const GOOGLE_CHAT_WEBHOOK = process.env.GOOGLE_CHAT_WEBHOOK ||
  'https://chat.googleapis.com/v1/spaces/AAQA4-FhOUs/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=AR4WhFnnlJJQPYgQ8eaCw32RUpEjavi_dMo-0dXx5rA';

async function sendNotification(sub) {

  const blocks   = sub.gameBlocks || [];
  const gameList = [...new Set(blocks.map(b => b.game).filter(Boolean))].join(', ');
  const gameAbbr = blocks.length === 1 ? (blocks[0].game || '') : `${blocks.length} games`;

  const lines = [
    `🎰 *New Content Request*`,
    ``,
    `*Team Member:* ${sub.requestor}`,
    sub.guestName ? `*Guest(s) of Honor:* ${sub.guestName}` : null,
    sub.occasion  ? `*Occasion:* ${sub.occasion}`           : null,
    `*Location:* ${sub.storeName}`,
    `*Event Date:* ${fmtDate(sub.eventDate)}`,
    `*Games:* ${gameList || '—'}`,
    sub.notes ? `*Notes:* ${sub.notes}` : null,
  ].filter(Boolean).join('\n');

  const res = await fetch(GOOGLE_CHAT_WEBHOOK, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ text: lines }),
  });

  if (!res.ok) throw new Error(`Google Chat webhook returned ${res.status}`);
  console.log(`✅ Google Chat notification sent (${gameAbbr})`);
}

// ── Utils ───────────────────────────────────────────────────
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtDate(str) {
  if (!str) return '—';
  const [y,m,d] = str.split('-');
  const M = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${M[+m-1]} ${+d}, ${y}`;
}

function genId() {
  return `REQ-${Date.now()}-${Math.floor(Math.random()*1000)}`;
}

// ── Routes ──────────────────────────────────────────────────

// Submit a new content request
app.post('/api/submit', async (req, res) => {
  const { requestor, guestName, occasion, storeName, eventDate, gameBlocks, notes } = req.body;

  if (!requestor || !storeName || !eventDate) {
    return res.status(400).json({ error: 'Requestor, store name, and event date are required.' });
  }

  if (!Array.isArray(gameBlocks) || gameBlocks.length === 0) {
    return res.status(400).json({ error: 'At least one game content block is required.' });
  }

  const sub = {
    id:         genId(),
    requestor:  requestor.trim(),
    guestName:  guestName ? guestName.trim() : '',
    occasion:   occasion  ? occasion.trim()  : '',
    storeName:  storeName.trim(),
    eventDate,
    gameBlocks: gameBlocks.map(b => ({
      game:   b.game || '',
      fields: b.fields || {},
    })),
    notes:      notes ? notes.trim() : '',
    submittedAt: new Date().toISOString(),
    status:     'New',
  };

  const data = load();
  data.unshift(sub);
  save(data);

  sendNotification(sub).catch(err => console.error('Notification error:', err.message));

  res.json({ success: true, id: sub.id });
});

// Get all submissions
app.get('/api/submissions', (req, res) => {
  res.json(load());
});

// Get one submission
app.get('/api/submissions/:id', (req, res) => {
  const s = load().find(x => x.id === req.params.id);
  if (!s) return res.status(404).json({ error: 'Not found' });
  res.json(s);
});

// Update status
app.patch('/api/submissions/:id/status', (req, res) => {
  const { status } = req.body;
  if (!['New','In Review','Completed'].includes(status)) {
    return res.status(400).json({ error: 'Invalid status' });
  }
  const data = load();
  const idx  = data.findIndex(x => x.id === req.params.id);
  if (idx === -1) return res.status(404).json({ error: 'Not found' });
  data[idx].status = status;
  save(data);
  res.json({ success: true });
});

// Test notification — visit /api/test-notify in browser to send a test message
app.get('/api/test-notify', async (req, res) => {
  try {
    const response = await fetch(GOOGLE_CHAT_WEBHOOK, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ text: '✅ *Test notification from GBGS Content Request Portal* — notifications are working!' }),
    });
    if (!response.ok) return res.json({ ok: false, error: `Webhook returned ${response.status}` });
    res.json({ ok: true, message: 'Test notification sent to Google Chat!' });
  } catch (err) {
    res.json({ ok: false, error: err.message });
  }
});

// Hub config
app.get('/api/config', (req, res) => {
  res.json({ hubPasswordRequired: true });
});

// Hub auth
app.post('/api/hub-auth', (req, res) => {
  const { password } = req.body;
  const required = process.env.HUB_PASSWORD || '4247';
  if (password === required) {
    res.json({ success: true });
  } else {
    res.status(401).json({ error: 'Incorrect password' });
  }
});

// Fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ── Start ───────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n🎰 Great Big Game Show — Content Request Portal`);
  console.log(`   Running at http://localhost:${PORT}`);
  console.log(`\n── Environment Check ──────────────────────────`);
  console.log(`   GOOGLE_CHAT_WEBHOOK : ${process.env.GOOGLE_CHAT_WEBHOOK ? '✅ SET' : '❌ NOT SET — notifications disabled'}`);
  console.log(`   PORT           : ${PORT}`);
  console.log(`───────────────────────────────────────────────\n`);
  try {
    fs.mkdirSync(path.dirname(DATA), { recursive: true });
    console.log(`   ✅ Data directory ready`);
  } catch (e) {
    console.error(`   ❌ Data directory error: ${e.message}`);
  }
});
