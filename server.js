require('dotenv').config();
const express  = require('express');
const { Resend } = require('resend');
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

// ── Email ───────────────────────────────────────────────────
async function sendEmail(sub) {
  if (!process.env.RESEND_API_KEY) {
    console.log('⚠️  Email not configured — set RESEND_API_KEY to enable notifications.');
    return;
  }

  const resend = new Resend(process.env.RESEND_API_KEY);

  // Field labels for email display
  const FIELD_LABELS = {
    question:'Question', grade:'Grade Level', correctAnswer:'Correct Answer',
    explanation:'Explanation', answerA:'Answer A', answerB:'Answer B',
    answerC:'Answer C', answerD:'Answer D',
    answerAExplanation:'Answer A Explanation', answerBExplanation:'Answer B Explanation',
    answerCExplanation:'Answer C Explanation', pointLevel:'Point Level',
    category:'Category', answer:'Answer',
    questionOne:'Question 1', answerOne:'Answer 1', questionTwo:'Question 2', answerTwo:'Answer 2',
    questionThree:'Question 3', answerThree:'Answer 3', questionFour:'Question 4', answerFour:'Answer 4',
  };

  // Game head colors
  const GAME_COLORS = {
    'Trivia Temple':           '#f59e0b',
    'The Grid — Categories':   '#3b82f6',
    'The Grid — Wisdom Wager': '#6366f1',
    "It's Elementary":         '#10b981',
    'Ready, Bet, Go':          '#ef4444',
  };

  const blocks = sub.gameBlocks || [];

  const blocksHtml = blocks.map((b, i) => {
    const color  = GAME_COLORS[b.game] || '#888';
    const fields = b.fields || {};
    const rows   = Object.entries(fields)
      .filter(([k, v]) => v && !k.startsWith('_'))
      .map(([k, v], ri) => `
        <tr style="background:${ri % 2 === 0 ? '#f9f9f9' : '#fff'}">
          <td style="padding:8px 12px;font-size:12px;font-weight:700;color:#555;width:38%;border-bottom:1px solid #eee">${esc(FIELD_LABELS[k] || k)}</td>
          <td style="padding:8px 12px;font-size:13px;color:#333;border-bottom:1px solid #eee;white-space:pre-wrap">${esc(v)}</td>
        </tr>`).join('');

    return `
      <div style="margin-bottom:16px;border-radius:6px;overflow:hidden;border:1px solid #e0e0e0">
        <div style="background:${color};padding:10px 16px;color:#fff;font-size:13px;font-weight:700">
          Block ${i + 1} — ${esc(b.game || '—')}
        </div>
        <table width="100%" cellpadding="0" cellspacing="0">${rows}</table>
      </div>`;
  }).join('');

  const gameList = [...new Set(blocks.map(b => b.game).filter(Boolean))].join(', ');

  const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;font-family:'Helvetica Neue',Arial,sans-serif;background:#f2f2f2">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:36px 0">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.1)">

      <tr>
        <td style="background:#08081a;padding:24px 32px;text-align:center">
          <div style="font-size:26px;margin-bottom:6px">🎰</div>
          <h1 style="margin:0;color:#f5c518;font-size:20px;letter-spacing:2px;text-transform:uppercase">Great Big Game Show</h1>
          <p style="margin:6px 0 0;color:#7070a0;font-size:12px;letter-spacing:1px">New Content Request</p>
        </td>
      </tr>

      <tr>
        <td style="padding:28px 32px">
          <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e0e0e0;border-radius:6px;overflow:hidden;margin-bottom:24px">
            <tr style="background:#fafafa">
              <td style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#999;font-weight:700;width:38%">Requestor</td>
              <td style="padding:10px 14px;font-size:15px;color:#111;font-weight:700">${esc(sub.requestor)}</td>
            </tr>
            ${sub.guestName ? `<tr>
              <td style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#999;font-weight:700;border-top:1px solid #eee">Guest Name</td>
              <td style="padding:10px 14px;font-size:15px;color:#111;font-weight:600;border-top:1px solid #eee">${esc(sub.guestName)}</td>
            </tr>` : ''}
            ${sub.occasion ? `<tr style="background:#fafafa">
              <td style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#999;font-weight:700;border-top:1px solid #eee">Occasion</td>
              <td style="padding:10px 14px;font-size:15px;color:#111;font-weight:600;border-top:1px solid #eee">${esc(sub.occasion)}</td>
            </tr>` : ''}
            <tr${sub.occasion || sub.guestName ? '' : ' style="background:#fafafa"'}>
              <td style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#999;font-weight:700;border-top:1px solid #eee">Store</td>
              <td style="padding:10px 14px;font-size:15px;color:#111;font-weight:700;border-top:1px solid #eee">${esc(sub.storeName)}</td>
            </tr>
            <tr>
              <td style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#999;font-weight:700;border-top:1px solid #eee">Event Date</td>
              <td style="padding:10px 14px;font-size:15px;color:#111;font-weight:600;border-top:1px solid #eee">${fmtDate(sub.eventDate)}</td>
            </tr>
            <tr style="background:#fafafa">
              <td style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#999;font-weight:700;border-top:1px solid #eee">Games</td>
              <td style="padding:10px 14px;font-size:13px;color:#333;border-top:1px solid #eee">${esc(gameList || '—')}</td>
            </tr>
            <tr>
              <td style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#999;font-weight:700;border-top:1px solid #eee">Submitted</td>
              <td style="padding:10px 14px;font-size:13px;color:#555;border-top:1px solid #eee">${new Date(sub.submittedAt).toLocaleString()}</td>
            </tr>
            ${sub.notes ? `<tr style="background:#fafafa">
              <td style="padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#999;font-weight:700;border-top:1px solid #eee">Notes</td>
              <td style="padding:10px 14px;font-size:13px;color:#555;border-top:1px solid #eee;white-space:pre-wrap">${esc(sub.notes)}</td>
            </tr>` : ''}
          </table>

          <h3 style="margin:0 0 12px;font-size:12px;text-transform:uppercase;letter-spacing:1.5px;color:#999;font-weight:700">
            ${blocks.length} Game Content Block${blocks.length !== 1 ? 's' : ''}
          </h3>
          ${blocksHtml}
        </td>
      </tr>

      <tr>
        <td style="background:#f7f7f7;padding:16px 32px;border-top:1px solid #eee;text-align:center">
          <p style="margin:0;font-size:11px;color:#aaa">View all submissions in the Content Request Hub</p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body></html>`;

  const gameAbbr = blocks.length === 1 ? (blocks[0].game || '') : `${blocks.length} games`;
  const toEmail  = process.env.NOTIFY_EMAIL || 'troy.armstrong@greatbiggameshow.com';

  const { error } = await resend.emails.send({
    from: 'GBGS Content Portal <onboarding@resend.dev>',
    to:   toEmail,
    subject: `📋 Content Request — ${sub.requestor} | ${sub.storeName} | ${fmtDate(sub.eventDate)} | ${gameAbbr}`,
    html,
  });

  if (error) throw new Error(error.message);
  console.log(`✅ Notification sent to ${toEmail}`);
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

  sendEmail(sub).catch(err => console.error('Email error:', err.message));

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

// Test email endpoint — visit /api/test-email in browser to trigger a test
app.get('/api/test-email', async (req, res) => {
  if (!process.env.RESEND_API_KEY) {
    return res.json({ ok: false, error: 'RESEND_API_KEY environment variable is not set.' });
  }
  try {
    const resend  = new Resend(process.env.RESEND_API_KEY);
    const toEmail = process.env.NOTIFY_EMAIL || 'troy.armstrong@greatbiggameshow.com';
    const { error } = await resend.emails.send({
      from: 'GBGS Content Portal <onboarding@resend.dev>',
      to:   toEmail,
      subject: '✅ Test Email — GBGS Content Portal',
      html: '<p>This is a test email from the Great Big Game Show Content Request Portal. If you received this, email notifications are working correctly!</p>',
    });
    if (error) return res.json({ ok: false, error: error.message });
    res.json({ ok: true, message: `Test email sent to ${toEmail}` });
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
  console.log(`\n🎰 Great Big Game Show — Content Request Portal  [v2 — mkdirSync fix active]`);
  console.log(`   Running at http://localhost:${PORT}`);
  console.log(`   Form:     http://localhost:${PORT}`);
  console.log(`   Hub:      http://localhost:${PORT}/hub.html`);
  console.log(`\n   Configure email by copying .env.example → .env\n`);
  // Proactively verify the data directory is writable at startup
  try {
    fs.mkdirSync(path.dirname(DATA), { recursive: true });
    console.log(`   ✅ Data directory ready: ${path.dirname(DATA)}`);
  } catch (e) {
    console.error(`   ❌ Data directory error: ${e.message}`);
  }
});
