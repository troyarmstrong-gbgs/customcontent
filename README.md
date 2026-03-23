# TEG Content Request Portal

A custom web portal for stores to submit content requests for shows, with a central admin hub and email notifications.

---

## Quick Start

### 1. Prerequisites
- [Node.js](https://nodejs.org/) v16 or higher

### 2. Install dependencies
Open a terminal in this folder and run:
```bash
npm install
```

### 3. Configure email notifications
Copy the example config file and fill in your SMTP details:
```bash
cp .env.example .env
```
Then open `.env` and fill in your email credentials.

**Using Gmail?** You'll need an App Password:
1. Go to [myaccount.google.com](https://myaccount.google.com) → Security → 2-Step Verification → App Passwords
2. Generate a password for "Mail" and paste it into `SMTP_PASS`

### 4. Start the server
```bash
npm start
```

Then open your browser:
- **Submission Form** → http://localhost:3000
- **Admin Hub** → http://localhost:3000/hub.html

---

## Configuration (`.env`)

| Variable | Description |
|---|---|
| `PORT` | Port to run the server on (default: 3000) |
| `NOTIFY_EMAIL` | Email address that receives submission notifications |
| `SMTP_HOST` | SMTP server hostname (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port (usually `587`) |
| `SMTP_USER` | Your sending email address |
| `SMTP_PASS` | Your email password or App Password |
| `SMTP_FROM_NAME` | Display name in notification emails |
| `HUB_PASSWORD` | Optional password to protect the /hub page |

---

## Features

### Submission Form (`/`)
- Store name, event date, game selection (Trivia Temple, The Grid, It's Elementary, Ready Bet Go)
- Dynamic custom content section — add as many field/answer pairs as needed
- Optional additional notes
- Confirmation screen with reference ID after submission

### Admin Hub (`/hub.html`)
- Stats bar showing total, new, in-review, and completed counts
- Sortable, searchable, filterable table of all submissions
- Filter by game or status
- Click any row to open a full detail modal
- Update submission status (New → In Review → Completed) directly from the modal
- Optional password protection

### Email Notifications
- Beautifully formatted HTML email sent to `troy.armstrong@theescapegame.com` on every new submission
- Includes all submission details and a formatted table of custom content items

---

## Data Storage
Submissions are saved to `data/submissions.json` in the project folder. This file is created automatically on first run.

---

## Deploying to a Server
To run this on a server so all stores can access it:
1. Upload this folder to your server
2. Run `npm install` on the server
3. Configure your `.env` file
4. Use a process manager like [PM2](https://pm2.keymetrics.io/) to keep it running:
   ```bash
   npm install -g pm2
   pm2 start server.js --name teg-portal
   ```
5. Set up a reverse proxy (Nginx or Apache) to point your domain to `localhost:3000`
