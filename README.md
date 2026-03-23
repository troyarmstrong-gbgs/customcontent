# GBGS Content Request Portal

A web portal for stores to submit custom content requests for Great Big Game Show events, with a central admin hub and email notifications.

---

## Hosting Guide

### Why not Netlify?

Netlify is built for **static websites**. This app runs a **Node.js server** that saves data to disk and sends emails — Netlify can't do that. Use **Railway** instead (it's free to start and purpose-built for apps like this).

---

## Step 1 — Push to GitHub

1. Go to [github.com](https://github.com) and sign in (or create a free account)
2. Click **"New repository"** (the green button or the `+` menu)
3. Name it `gbgs-content-portal`, set it to **Private**, click **Create repository**
4. GitHub will show you a block of commands — open a terminal in your project folder and run:

```bash
git remote add origin https://github.com/YOUR-USERNAME/gbgs-content-portal.git
git push -u origin main
```

Your code is now on GitHub. ✅

---

## Step 2 — Deploy to Railway

Railway runs your Node.js server 24/7 so anyone on any network can access the form.

1. Go to [railway.app](https://railway.app) and sign up with your GitHub account
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your `gbgs-content-portal` repository
4. Railway will automatically detect it's a Node.js app and deploy it

### Set environment variables

Once deployed, click your service → **"Variables"** tab and add:

| Variable | Value |
|---|---|
| `PORT` | `3000` |
| `NOTIFY_EMAIL` | `troy.armstrong@theescapegame.com` |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | your Gmail App Password (see below) |
| `SMTP_FROM_NAME` | `GBGS Content Portal` |
| `HUB_PASSWORD` | a password to protect the admin hub (optional) |

### Gmail App Password setup
1. Go to [myaccount.google.com](https://myaccount.google.com) → Security → 2-Step Verification
2. Scroll to **App Passwords**, click it
3. Choose **Mail** → **Other** → type "GBGS Portal" → click Generate
4. Copy the 16-character password into `SMTP_PASS` on Railway

### Add a Volume (keeps your data safe across restarts)

1. In Railway, click your service → **"Volumes"** tab → **"Add Volume"**
2. Set the **Mount Path** to `/app/data`
3. Click **Add** — done. Your submissions will now survive server restarts.

### Get your public URL

In Railway, click your service → **"Settings"** → **"Networking"** → **"Generate Domain"**. You'll get a URL like `gbgs-content-portal.up.railway.app` — share this with your stores.

---

## Do I need a database?

**Short answer: not yet.** The app stores submissions as a JSON file. With Railway's Volume (set up above), this file persists safely across restarts. It handles hundreds of submissions easily.

If you ever need multi-user editing, search across thousands of records, or integrations with other tools, a proper database (PostgreSQL) would be the upgrade path — but that's a future problem.

---

## Running locally

```bash
npm install
cp .env.example .env   # fill in your SMTP details
npm start
```

- Form: http://localhost:3000
- Hub:  http://localhost:3000/hub.html

---

## Font setup (Tenon)

To use the official Tenon font:
1. Place your Tenon font files (`.woff2` and `.woff`) in `/public/fonts/`
2. Open `public/style.css` and uncomment the `@font-face` block near the top

Until then, Nunito (loaded from Google Fonts) is used as a close match.
 
