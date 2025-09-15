import os
import ssl
import imaplib
import smtplib
from typing import List, Dict, Optional, Tuple
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

# MCP SDK (install via requirements.txt)
from mcp.server.fastmcp import FastMCP
from mcp.server.websocket import websocket_server  # ASGI context manager for MCP over WebSocket
from urllib.parse import parse_qs
import argparse
import anyio
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

app = FastAPI()
mcp = FastMCP("gmx-mcp")

# 👇 ajoute ça pour répondre à ChatGPT
@app.get("/")
async def root():
    return {"mcp": "ok", "protocol": "MCP"}

# puis monte les outils MCP sur /
mcp.mount_to_fastapi(app, path="/")



IMAP_HOST = os.environ.get("GMX_IMAP_HOST", "imap.gmx.com")
IMAP_PORT = int(os.environ.get("GMX_IMAP_PORT", "993"))
SMTP_HOST = os.environ.get("GMX_SMTP_HOST", "mail.gmx.com")
SMTP_PORT = int(os.environ.get("GMX_SMTP_PORT", "587"))


class GmxClient:
    def __init__(self, email_addr: str, password: str):
        self.email = email_addr
        self.password = password

    # ---------- IMAP helpers ----------
    def _imap_connect(self) -> imaplib.IMAP4_SSL:
        ctx = ssl.create_default_context()
        return imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx)

    def list_messages(
        self,
        mailbox: str = "INBOX",
        limit: int = 10,
        unread_only: bool = False,
    ) -> List[Dict[str, str]]:
        imap = self._imap_connect()
        try:
            typ, _ = imap.login(self.email, self.password)
            if typ != "OK":
                raise RuntimeError("IMAP login failed")

            typ, _ = imap.select(mailbox, readonly=True)
            if typ != "OK":
                raise RuntimeError(f"Cannot select mailbox {mailbox}")

            criteria = "UNSEEN" if unread_only else "ALL"
            typ, data = imap.uid("search", None, criteria)
            if typ != "OK":
                raise RuntimeError("IMAP search failed")

            uids = (data[0] or b"").split()
            # Most recent first
            uids = list(reversed(uids))[: max(0, int(limit))]

            results: List[Dict[str, str]] = []
            for uid in uids:
                typ, fetch_data = imap.uid("fetch", uid, b"BODY.PEEK[HEADER]")
                if typ != "OK" or not fetch_data or fetch_data[0] is None:
                    continue

                raw = fetch_data[0][1]
                msg = BytesParser(policy=policy.default).parsebytes(raw)
                results.append(
                    {
                        "uid": uid.decode(),
                        "from": msg.get("From", ""),
                        "subject": msg.get("Subject", ""),
                        "date": msg.get("Date", ""),
                    }
                )
            return results
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    def _extract_bodies(self, msg) -> Tuple[Optional[str], Optional[str]]:
        text_part = None
        html_part = None
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get("Content-Disposition", "")).lower()
                if part.get_content_maintype() == "multipart":
                    continue
                if "attachment" in disp:
                    continue
                try:
                    payload = part.get_content()
                except:  # noqa: E722
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, (bytes, bytearray)):
                        try:
                            payload = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                        except Exception:
                            payload = payload.decode("utf-8", errors="replace")
                if ctype == "text/plain" and text_part is None:
                    text_part = str(payload)
                elif ctype == "text/html" and html_part is None:
                    html_part = str(payload)
        else:
            ctype = msg.get_content_type()
            try:
                body = msg.get_content()
            except:  # noqa: E722
                body = msg.get_payload(decode=True)
                if isinstance(body, (bytes, bytearray)):
                    body = body.decode(msg.get_content_charset() or "utf-8", errors="replace")
            if ctype == "text/html":
                html_part = str(body)
            else:
                text_part = str(body)
        return text_part, html_part

    def read_message(
        self, uid: str, mailbox: str = "INBOX", mark_seen: bool = False
    ) -> Dict[str, Optional[str]]:
        imap = self._imap_connect()
        try:
            typ, _ = imap.login(self.email, self.password)
            if typ != "OK":
                raise RuntimeError("IMAP login failed")

            typ, _ = imap.select(mailbox, readonly=not mark_seen)
            if typ != "OK":
                raise RuntimeError(f"Cannot select mailbox {mailbox}")

            fetch_part = b"RFC822" if mark_seen else b"BODY.PEEK[]"
            typ, fetch_data = imap.uid("fetch", uid.encode(), fetch_part)
            if typ != "OK" or not fetch_data or fetch_data[0] is None:
                raise RuntimeError(f"Message uid {uid} not found")

            raw = fetch_data[0][1]
            msg = BytesParser(policy=policy.default).parsebytes(raw)
            text_part, html_part = self._extract_bodies(msg)

            return {
                "uid": uid,
                "subject": msg.get("Subject", ""),
                "from": msg.get("From", ""),
                "to": msg.get("To", ""),
                "date": msg.get("Date", ""),
                "text": text_part,
                "html": html_part,
            }
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    # ---------- SMTP helpers ----------
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        content_type: str = "plain",
    ) -> str:
        if content_type not in ("plain", "html"):
            raise ValueError("content_type must be 'plain' or 'html'")

        msg = EmailMessage()
        msg["From"] = self.email
        msg["To"] = to
        msg["Subject"] = subject
        subtype = "html" if content_type == "html" else "plain"
        msg.set_content(body, subtype=subtype)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(self.email, self.password)
            smtp.send_message(msg)

        return "sent"


def get_client() -> GmxClient:
    email_addr = os.environ.get("GMX_EMAIL")
    password = os.environ.get("GMX_PASSWORD")
    if not email_addr or not password:
        raise RuntimeError("GMX_EMAIL and GMX_PASSWORD must be set in environment")
    return GmxClient(email_addr, password)


# ---------- MCP Server ----------
mcp = FastMCP("gmx-mail")


@mcp.tool()
def list_messages(mailbox: str = "INBOX", limit: int = 10, unread_only: bool = False) -> List[Dict[str, str]]:
    """List recent messages in a mailbox.

    Args:
        mailbox: Mailbox name (default INBOX)
        limit: Max number of messages to return
        unread_only: If true, only return UNSEEN messages
    Returns:
        List of dicts with uid, from, subject, date
    """
    client = get_client()
    return client.list_messages(mailbox=mailbox, limit=limit, unread_only=unread_only)


@mcp.tool()
def read_message(uid: str, mailbox: str = "INBOX", mark_seen: bool = False) -> Dict[str, Optional[str]]:
    """Read a specific message by IMAP UID.

    Args:
        uid: IMAP UID of the message
        mailbox: Mailbox name (default INBOX)
        mark_seen: If true, mark the message as seen
    Returns:
        Dict with headers and text/html bodies
    """
    client = get_client()
    return client.read_message(uid=uid, mailbox=mailbox, mark_seen=mark_seen)


@mcp.tool()
def send_email(to: str, subject: str, body: str, content_type: str = "plain") -> str:
    """Send an email via GMX SMTP.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body
        content_type: 'plain' or 'html'
    Returns:
        'sent' if successfully sent
    """
    client = get_client()
    return client.send_email(to=to, subject=subject, body=body, content_type=content_type)


def _run_stdio():
    mcp.run()


def _run_http(host: str, port: int, mount_path: str):
    # Configure FastMCP HTTP host/port/mount dynamically
    mcp.settings.host = host
    mcp.settings.port = port
    # Toujours exposer MCP à la racine "/"
    mcp.settings.mount_path = "/"
    # Run Streamable HTTP (compatible avec ChatGPT Agent Mode)
    anyio.run(mcp.run_streamable_http_async)

def _run_ws(host: str, port: int, mount_path: str):
    # Minimal ASGI app that serves MCP over WebSocket at the root path
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Mount
    import uvicorn

    async def asgi_app(scope, receive, send):
        if scope["type"] == "websocket":
            # Optional jeton de sécurité via query param ?token=...
            required = os.environ.get("MCP_TOKEN")
            if required:
                try:
                    qs = parse_qs((scope.get("query_string") or b"").decode())
                    token = (qs.get("token") or [None])[0]
                except Exception:
                    token = None
                if token != required:
                    # Close without accepting
                    await send({"type": "websocket.close", "code": 1008})
                    return

            async with websocket_server(scope, receive, send) as (read_stream, write_stream):
                await mcp._mcp_server.run(  # type: ignore[attr-defined]
                    read_stream,
                    write_stream,
                    mcp._mcp_server.create_initialization_options(),  # type: ignore[attr-defined]
                )
        else:
            # Basic 404 for HTTP requests
            response = PlainTextResponse("Not Found", status_code=404)
            await response(scope, receive, send)

    # Mount path support
    app = Starlette(routes=[Mount(mount_path or "/", app=asgi_app)])

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    anyio.run(server.serve)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GMX MCP Server (STDIO, HTTP(SSE)/Streamable, WebSocket)")
    parser.add_argument(
        "--mode",
        choices=["stdio", "http", "sse", "ws"],
        default=os.environ.get("MCP_MODE", "stdio"),
        help="Mode d'exécution: stdio (par défaut), http (Streamable HTTP), sse, ou ws (WebSocket)",
    )
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "3333")))
    parser.add_argument("--path", default=os.environ.get("MCP_PATH", "/"))
    args = parser.parse_args()

    if args.mode == "http":
        _run_http(args.host, args.port, args.path)
    elif args.mode == "sse":
        # SSE utilise également host/port; path désigne le mount_path
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        # Pour compatibilité avec certains clients MCP (dont ChatGPT),
        # expose le flux SSE directement à la racine si le path est "/".
        if (args.path or "/") == "/":
            try:
                mcp.settings.message_path = "/"  # type: ignore[attr-defined]
            except Exception:
                pass
        anyio.run(lambda: mcp.run_sse_async(args.path))
    elif args.mode == "ws":
        _run_ws(args.host, args.port, args.path)
    else:
        _run_stdio()
