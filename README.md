# GMX Mail MCP Server (Python)

MCP server that connects to your GMX mailbox using IMAP/SMTP and exposes tools to list, read, and send email. You can add this server to ChatGPT’s Agent Mode (MCP) to let an agent interact with your mailbox.

## Features
- List recent messages (optionally unread only)
- Read a specific message by UID
- Send email via GMX SMTP
- Basic mailbox selection (default `INBOX`)

## Requirements
- Python 3.9+
- `pip install -r requirements.txt`
- GMX credentials available via environment variables:
  - `GMX_EMAIL` (e.g., `yourname@gmx.com`)
  - `GMX_PASSWORD` (recommend using an app-specific password if available)

## Install
```powershell
cd mcp-gmx-mail
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If using a system Python on Windows without a venv, you can also just:
```powershell
pip install -r requirements.txt
```

## Configure Environment
Set your credentials as environment variables. For Windows PowerShell:
```powershell
$env:GMX_EMAIL = "yourname@gmx.com"
$env:GMX_PASSWORD = "your-app-password-or-password"
```

GMX Servers used:
- IMAP: `imap.gmx.com` port `993` (SSL)
- SMTP: `mail.gmx.com` port `587` (STARTTLS)

## Run (local test)
You can run the server over stdio to test basic startup:
```powershell
python server.py
```
It will wait for an MCP client over stdio. To explore manually you can use an MCP inspector client or connect via ChatGPT’s Agent Mode as shown below.

### Run as HTTP server (URL mode)
Exposer une URL HTTP que ChatGPT peut utiliser (Streamable HTTP):
```powershell
pip install -r requirements.txt
python server.py --mode http --host 127.0.0.1 --port 3333 --path /
```
Your MCP server URL will be: `http://127.0.0.1:3333/`

### Run as WebSocket server (URL mode)
Exposer une URL WebSocket (souvent acceptée par l’UI Agent Mode):
```powershell
python server.py --mode ws --host 127.0.0.1 --port 3337 --path /
```
URL: `ws://127.0.0.1:3337/`

## Tools
- `list_messages(mailbox='INBOX', limit=10, unread_only=False)`
  - Returns recent messages with: `uid`, `from`, `subject`, `date`.
- `read_message(uid: str, mailbox='INBOX', mark_seen=False)`
  - Returns parsed `subject`, `from`, `to`, `date`, and `text`/`html` bodies.
- `send_email(to: str, subject: str, body: str, content_type='plain')`
  - Sends an email via SMTP; `content_type` can be `plain` or `html`.

## Add to ChatGPT Agent Mode (MCP)
In ChatGPT:
Option A — Local (STDIO, sans URL):
1. Paramètres → Avancé → Model Context Protocol (MCP) → Ajouter un serveur local
2. Nom: `gmx-mail`
3. Commande: `python`
4. Arguments: `server.py`
5. Répertoire de travail: chemin absolu vers `mcp-gmx-mail`
6. Variables d’environnement:
   - `GMX_EMAIL`: votre adresse GMX
   - `GMX_PASSWORD`: votre mot de passe (ou mot de passe d’application)

Option B — URL HTTP:
1. Paramètres → Avancé → Model Context Protocol (MCP) → Ajouter un serveur MCP par URL
2. URL: `http://127.0.0.1:3333/`
3. Lancez le serveur dans PowerShell: `python server.py --mode http --host 127.0.0.1 --port 3333 --path /`
4. Variables d’environnement: définissez-les dans votre shell avant de lancer le serveur (`GMX_EMAIL`, `GMX_PASSWORD`).

Option C — URL WebSocket:
1. Paramètres → Avancé → Model Context Protocol (MCP) → Ajouter un serveur MCP par URL
2. URL: `ws://127.0.0.1:3337/`
3. Lancez le serveur dans PowerShell: `python server.py --mode ws --host 127.0.0.1 --port 3337 --path /`
4. Authentification: Aucune

## Déploiement public (recommandé si l’UI refuse les URLs locales)

### Render (hébergement gratuit)
- Préparez un repo GitHub contenant ce dossier `mcp-gmx-mail` (incluant Procfile et render.yaml).
- Sur https://dashboard.render.com/ → New → Blueprint → pointez vers votre repo.
- Render lit `render.yaml` et crée un service Web.
- Dans l’onglet Environment du service, ajoutez les variables:
  - `GMX_EMAIL`
  - `GMX_PASSWORD`
- Déploiement: Render installe `requirements.txt` et lance: `python server.py --mode http --host 0.0.0.0 --port $PORT --path /`.
- Une URL publique HTTPS est fournie (ex: `https://gmx-mcp.onrender.com`).

Dans ChatGPT (MCP par URL):
- URL: votre URL Render (HTTPS)
- Authentification: Aucune

Notes:
- Render supporte SSE/HTTP nécessaires au transport MCP. Si l’UI exige WebSocket, lancez le serveur en mode `ws` localement et exposez via un tunnel WSS, ou adaptez un déploiement avec ASGI WebSocket (nécessite configuration avancée).

Save, then enable the server for your agent. The tools will appear as actions the agent can call.

## Security Notes
- Prefer app-specific passwords if your GMX account supports them.
- Avoid committing credentials; use environment variables or your OS secret store.
- The server only connects to GMX when a tool is called and closes connections afterwards.

## Limitations
- Uses Python’s standard `imaplib`/`smtplib` (blocking); for MCP usage this is fine, as calls are short-lived.
- Not all IMAP edge cases are handled. If you need flags/labels or advanced search, extend the helpers.

## License
No license specified. Private/local use assumed.
