#!/usr/bin/env python3
"""Local browser UI for sending IDTag test pushes over the TCP socket."""

import json
import os
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name(".push_test_ui.json")
UI_HOST = "127.0.0.1"
UI_PORT = 8765
DEFAULTS = {
    "host": "211.23.22.158",
    "port": 7002,
    "secret": "",
    "card_number": "AACC0102030405",
    "title": "iTag 推播測試",
    "body": "這是一則從本機測試工具送出的推播通知。",
}


HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>iTag 推播測試工具</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0; min-height: 100vh; padding: 40px 20px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #18332d;
      background: linear-gradient(145deg, #e7f4ef 0%, #f5f8f7 50%, #d8ece5 100%);
    }
    .shell { width: min(720px, 100%); margin: 0 auto; }
    .header { margin-bottom: 20px; }
    h1 { margin: 0 0 8px; font-size: 32px; letter-spacing: .02em; }
    .card {
      background: rgba(255,255,255,.94); border: 1px solid rgba(21,128,105,.16);
      border-radius: 20px; padding: 26px; box-shadow: 0 18px 50px rgba(28,73,62,.12);
    }
    .connection {
      display: flex; align-items: center; gap: 9px; margin-bottom: 22px;
      padding: 11px 14px; border-radius: 12px; background: #edf3f1; color: #49615a;
      font-size: 14px;
    }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: #a1aaa7; }
    .connection.online { background: #e5f7ef; color: #116149; }
    .connection.online .dot { background: #18a474; box-shadow: 0 0 0 4px rgba(24,164,116,.13); }
    label { display: block; margin: 16px 0 7px; font-size: 14px; font-weight: 700; }
    input, textarea {
      width: 100%; border: 1px solid #b9cbc5; border-radius: 11px;
      padding: 13px 14px; font: inherit; color: #18332d; background: white;
      outline: none; transition: border-color .15s, box-shadow .15s;
    }
    input:focus, textarea:focus { border-color: #168974; box-shadow: 0 0 0 3px rgba(22,137,116,.12); }
    textarea { min-height: 150px; resize: vertical; }
    button {
      width: 100%; border: 0; border-radius: 12px; padding: 15px 18px; margin-top: 22px;
      background: #168974; color: white; font-size: 17px; font-weight: 800;
      cursor: pointer; transition: transform .1s, background .15s;
    }
    button:hover { background: #0f7563; }
    button:active { transform: translateY(1px); }
    button:disabled { background: #8da8a1; cursor: wait; }
    .result { display: none; margin-top: 18px; padding: 14px; border-radius: 12px; line-height: 1.5; }
    .result.ok { display: block; background: #e4f6ed; color: #126247; }
    .result.error { display: block; background: #fff0ef; color: #9b2f29; }
    .hint { margin: 18px 2px 0; color: #64766f; font-size: 13px; text-align: center; }
    code { word-break: break-all; }
  </style>
</head>
<body>
  <main class="shell">
    <div class="header">
      <h1>iTag 推播測試工具</h1>
    </div>
    <section class="card">
      <div id="connection" class="connection"><span class="dot"></span><span>正在檢查連線…</span></div>
      <form id="pushForm">
        <label for="cardNumber">卡號</label>
        <input id="cardNumber" name="card_number" autocomplete="off" required>
        <label for="title">推播標題</label>
        <input id="title" name="title" required>
        <label for="body">推播內容</label>
        <textarea id="body" name="body" required></textarea>
        <button id="sendButton" type="submit">傳送推播</button>
      </form>
      <div id="result" class="result"></div>
      <p class="hint">推播註冊與傳送皆由遠端服務器處理，本頁不包含 Firebase 私密金鑰。</p>
    </section>
  </main>
  <script>
    const form = document.getElementById('pushForm');
    const button = document.getElementById('sendButton');
    const result = document.getElementById('result');
    const connection = document.getElementById('connection');

    async function loadConfig() {
      const response = await fetch('/api/config');
      const config = await response.json();
      document.getElementById('cardNumber').value = config.card_number || '';
      document.getElementById('title').value = config.title || '';
      document.getElementById('body').value = config.body || '';
    }

    async function checkConnection() {
      try {
        const response = await fetch('/api/status', {cache: 'no-store'});
        const status = await response.json();
        connection.className = status.connected ? 'connection online' : 'connection';
        connection.lastElementChild.textContent = status.connected
          ? `已連線到推播服務器（${status.host}:${status.port}）`
          : '尚未連線，請確認外網 7002 連接埠';
      } catch (_) {
        connection.className = 'connection';
        connection.lastElementChild.textContent = '本機 UI 服務連線失敗';
      }
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      button.disabled = true;
      button.textContent = '傳送中…';
      result.className = 'result';
      const payload = Object.fromEntries(new FormData(form).entries());
      try {
        const response = await fetch('/api/send', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '推播請求失敗');
        result.className = 'result ok';
        result.innerHTML = `已送出，目標裝置 <strong>${data.target_count}</strong> 台<br>` +
          `通知 ID：<code>${data.notification_id}</code>`;
      } catch (error) {
        result.className = 'result error';
        result.textContent = `傳送失敗：${error.message}`;
      } finally {
        button.disabled = false;
        button.textContent = '傳送推播';
      }
    });

    loadConfig();
    checkConnection();
    setInterval(checkConnection, 3000);
  </script>
</body>
</html>
"""


def load_config():
    config = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                config.update(saved)
        except (OSError, ValueError):
            pass
    config["secret"] = os.environ.get("IDTAG_SOCKET_SECRET", config["secret"])
    return config


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CONFIG_PATH.chmod(0o600)


def send_push(host, port, secret, card_number, title, body):
    payload = {
        "secret": secret, "card_number": card_number,
        "title": title, "body": body, "data": {},
    }
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
    with socket.create_connection((host, port), timeout=10) as connection:
        connection.sendall(encoded)
        connection.settimeout(15)
        response_line = connection.makefile("rb").readline(65537)
    if not response_line:
        raise RuntimeError("伺服器未回應")
    response = json.loads(response_line.decode("utf-8"))
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error", "推播請求失敗")))
    return response


class PushUIHandler(BaseHTTPRequestHandler):
    server_version = "IDTagPushUI/1.0"

    def log_message(self, _format, *_args):
        return

    def _send_json(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/":
            encoded = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)
            return
        if self.path == "/api/config":
            config = load_config()
            self._send_json(200, {key: config[key] for key in ("card_number", "title", "body")})
            return
        if self.path == "/api/status":
            config = load_config()
            connected = False
            try:
                with socket.create_connection((str(config["host"]), int(config["port"])), timeout=1):
                    connected = True
            except (OSError, ValueError):
                pass
            self._send_json(200, {"connected": connected, "host": config["host"], "port": config["port"]})
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/api/send":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 64 * 1024:
                raise ValueError("請求內容大小錯誤")
            values = json.loads(self.rfile.read(length).decode("utf-8"))
            config = load_config()
            card_number = str(values.get("card_number", "")).strip().upper()
            title = str(values.get("title", "")).strip()
            body = str(values.get("body", "")).strip()
            if not card_number or not title or not body:
                raise ValueError("卡號、標題與內容都必須填寫")
            config.update({"card_number": card_number, "title": title, "body": body})
            save_config(config)
            response = send_push(
                str(config["host"]), int(config["port"]), str(config["secret"]),
                card_number, title, body,
            )
            self._send_json(200, response)
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            self._send_json(400, {"ok": False, "error": str(error)})


def main():
    server = ThreadingHTTPServer((UI_HOST, UI_PORT), PushUIHandler)
    url = f"http://{UI_HOST}:{UI_PORT}/"
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print(f"iTag 推播測試工具：{url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
