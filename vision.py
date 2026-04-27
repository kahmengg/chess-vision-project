"""
vision.py — Board State Reader
============================================================
Reads the current chess position as a FEN string.

Strategy: chess.com encodes every piece in the page HTML as divs like
    <div class="piece wp sq45"></div>
    
We use Python's built-in http client to talk to Chrome's DevTools
Protocol (CDP) which lets us run JavaScript in the page to read those
divs — without needing Selenium or any special Chrome launch flags,
because we open Chrome ourselves via subprocess.

If Chrome is already open: we find it via the debug port.
If not: we launch it ourselves with the debug port.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
import urllib.error
from typing import Optional, Tuple, Dict, Any
import sys
import os
import tempfile

from config import Config

PIECE_MAP = {
    "wk": "K", "wq": "Q", "wr": "R", "wb": "B", "wn": "N", "wp": "P",
    "bk": "k", "bq": "q", "br": "r", "bb": "b", "bn": "n", "bp": "p",
}

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(
        os.environ.get("USERNAME", "")),
]

DEBUG_PORT = 9222


class VisionModule:
    def __init__(self, config: Config):
        self.config = config
        self._tab_ws_url = None
        self._last_debug: Dict[str, Any] = {
            "status": "init",
            "raw_nodes": 0,
            "placed": 0,
            "message": "Starting vision module",
        }
        self._ensure_chrome_and_connect()

    def get_last_debug(self) -> Dict[str, Any]:
        return dict(self._last_debug)

    def _set_debug(self, **kwargs):
        self._last_debug.update(kwargs)

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _ensure_chrome_and_connect(self):
        """Connect to existing Chrome debug port, or launch Chrome if needed."""
        # Try connecting to already-open Chrome first
        if self._try_connect():
            return

        # Chrome not running with debug port — launch it ourselves
        print("[Vision] Chrome not found on debug port. Launching Chrome...")
        self._launch_chrome()

        # Wait up to 10s for Chrome to start
        for i in range(10):
            time.sleep(1)
            print(f"[Vision] Waiting for Chrome to start... ({i+1}s)")
            if self._try_connect():
                return

        raise RuntimeError(
            "\n[Vision] Could not connect to Chrome after launching.\n"
            "Please open Chrome manually, go to chess.com, start a game, "
            "then run main.py again.\n"
        )

    def _launch_chrome(self):
        chrome_exe = None
        for path in CHROME_PATHS:
            if os.path.isfile(path):
                chrome_exe = path
                break

        if not chrome_exe:
            raise FileNotFoundError(
                "\n[Vision] Chrome not found. Please install Google Chrome.\n"
                "Or open Chrome manually with:\n"
                f'  chrome.exe --remote-debugging-port={DEBUG_PORT}\n'
            )

        # Chrome ignores remote-debugging flags when attaching to an already
        # running normal profile process. A dedicated user-data-dir forces a
        # separate debug-enabled instance.
        debug_profile = os.path.join(tempfile.gettempdir(), "chess_overlay_debug_profile")
        os.makedirs(debug_profile, exist_ok=True)

        subprocess.Popen([
            chrome_exe,
            f"--remote-debugging-port={DEBUG_PORT}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={debug_profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            "https://www.chess.com",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[Vision] Launched isolated debug Chrome profile. Opening chess.com...")

    def _try_connect(self) -> bool:
        """Try to find a chess.com tab via the CDP debug port."""
        try:
            url = f"http://localhost:{DEBUG_PORT}/json"
            with urllib.request.urlopen(url, timeout=3) as r:
                tabs = json.loads(r.read())

            game_hints = ("/play", "/game", "/live", "/analysis", "/bot")
            chess_pages = [
                t for t in tabs
                if t.get("type") == "page" and "chess.com" in t.get("url", "")
            ]

            # Prefer URLs that look like active game/analysis pages.
            preferred = [
                t for t in chess_pages
                if any(h in t.get("url", "") for h in game_hints)
            ]
            candidates = preferred or chess_pages

            for tab in candidates:
                ws_url = tab.get("webSocketDebuggerUrl")
                if not ws_url:
                    continue
                self._tab_ws_url = ws_url
                tab_url = tab.get("url", "")
                print(f"[Vision] Connected to: {tab_url[:90]}")
                return True

            # Debug port is reachable but no chess.com tab yet.
            if tabs:
                print("[Vision] Debug Chrome is reachable, but no chess.com tab is open yet.")
        except Exception:
            pass
        return False

    # ── Public interface ──────────────────────────────────────────────────────

    def capture(self, board_rect=None):
        return None  # Not needed — we read DOM directly

    def screenshot_to_fen(self, screenshot=None) -> Optional[str]:
        try:
            fen = self._read_fen_from_dom()
            if fen is None:
                # Rebind to the most game-like tab and retry once.
                self._try_connect()
                fen = self._read_fen_from_dom()
            return fen
        except Exception as e:
            print(f"[Vision] DOM read error: {e}")
            self._set_debug(status="error", message=f"DOM read error: {e}")
            # Try reconnecting
            self._try_connect()
            return None

    def get_board_rect_from_page(self) -> Optional[Tuple[int,int,int,int]]:
        """Get the board element's screen coordinates from the page."""
        js = """
        (function() {
            var b = document.querySelector('chess-board') ||
                    document.querySelector('.board-layout-chessboard') ||
                    document.querySelector('.board');
            if (!b) return null;
            var r = b.getBoundingClientRect();
            // Add window scroll offset to get screen coords
            return {
                left:   Math.round(r.left   + window.screenX + 50 ),
                top:    Math.round(r.top    + window.screenY + 90),
                right:  Math.round(r.right  + window.screenX - 20),
                bottom: Math.round(r.bottom + window.screenY + 90)
            };
        })()
        """
        result = self._run_js(js)
        if result:
            return (result["left"], result["top"],
                    result["right"], result["bottom"])
        return None

    def is_board_flipped(self) -> Optional[bool]:
        """Detect whether the chessboard is flipped for the black side."""
        js = """
        (function() {
            var b = document.querySelector('chess-board') ||
                    document.querySelector('.board-layout-chessboard') ||
                    document.querySelector('.board');
            if (!b) return null;

            var text = '';
            if (typeof b.className === 'string') text += b.className + ' ';
            if (b.parentElement && typeof b.parentElement.className === 'string') {
                text += b.parentElement.className + ' ';
            }
            if (b.dataset) {
                for (var k in b.dataset) {
                    text += String(b.dataset[k]) + ' ';
                }
            }
            text = text.toLowerCase();

            var style = '';
            try {
                style = window.getComputedStyle(b).transform || '';
            } catch (e) {
                style = '';
            }

            return {
                flipped: /(flipped|orientation-black|black-bottom|rotate\(180deg\))/.test(text) ||
                         (style && style.indexOf('matrix(-1') !== -1),
                text: text,
                style: style
            };
        })()
        """
        result = self._run_js(js)
        if isinstance(result, dict) and "flipped" in result:
            return bool(result["flipped"])
        return None

    # ── DOM reading ───────────────────────────────────────────────────────────

    def _read_fen_from_dom(self) -> Optional[str]:
        js = """
        (function() {
            function pieceCodeToFen(pc) {
                var map = {
                    wk:'K', wq:'Q', wr:'R', wb:'B', wn:'N', wp:'P',
                    bk:'k', bq:'q', br:'r', bb:'b', bn:'n', bp:'p'
                };
                return map[pc] || null;
            }

            function wordsToFen(text) {
                var isW = /\\bwhite\\b/.test(text);
                var isB = /\\bblack\\b/.test(text);
                if (!isW && !isB) return null;
                if (/\\bking\\b/.test(text))   return isW ? 'K' : 'k';
                if (/\\bqueen\\b/.test(text))  return isW ? 'Q' : 'q';
                if (/\\brook\\b/.test(text))   return isW ? 'R' : 'r';
                if (/\\bbishop\\b/.test(text)) return isW ? 'B' : 'b';
                if (/\\bknight\\b/.test(text)) return isW ? 'N' : 'n';
                if (/\\bpawn\\b/.test(text))   return isW ? 'P' : 'p';
                return null;
            }

            function extractSquare(text) {
                var m = text.match(/(?:sq|square-?)([1-8])([1-8])/);
                if (m) {
                    var f = parseInt(m[1], 10) - 1;
                    var r = parseInt(m[2], 10) - 1;
                    return {f:f, r:r};
                }
                m = text.match(/\\b([a-h])([1-8])\\b/);
                if (m) {
                    return {f:m[1].charCodeAt(0)-97, r:parseInt(m[2], 10)-1};
                }
                return null;
            }

            function extractPiece(text) {
                var m = text.match(/\\b(wk|wq|wr|wb|wn|wp|bk|bq|br|bb|bn|bp)\\b/);
                if (m) return pieceCodeToFen(m[1]);
                return wordsToFen(text);
            }

            function collectRoots(root, out) {
                out.push(root);
                var all = root.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    if (all[i].shadowRoot) collectRoots(all[i].shadowRoot, out);
                }
            }

            function collectBoardRoots(root) {
                var selectors = 'chess-board, .board-layout-chessboard, .board, [class*="board"]';
                var nodes = [];
                try {
                    nodes = Array.prototype.slice.call(root.querySelectorAll(selectors));
                } catch (e) {
                    nodes = [];
                }
                return nodes;
            }

            var roots = collectBoardRoots(document);
            if (!roots.length) {
                collectRoots(document, roots);
            }

            var placements = {};
            var rawNodes = 0;

            for (var r = 0; r < roots.length; r++) {
                var nodes = roots[r].querySelectorAll('.piece, [data-piece], [data-square], [class*="piece"], [class*="square-"]');
                for (var i = 0; i < nodes.length; i++) {
                    var n = nodes[i];
                    rawNodes += 1;

                    var cls = (typeof n.className === 'string') ? n.className : '';
                    var parentCls = (n.parentElement && typeof n.parentElement.className === 'string')
                        ? n.parentElement.className : '';
                    var attrs = '';
                    if (n.getAttribute) {
                        attrs = [
                            n.getAttribute('data-piece') || '',
                            n.getAttribute('data-square') || '',
                            n.getAttribute('data-test-element') || '',
                            n.getAttribute('aria-label') || '',
                        ].join(' ');
                    }
                    var text = (cls + ' ' + parentCls + ' ' + attrs).toLowerCase();

                    var sq = extractSquare(text);
                    if (!sq) continue;

                    var piece = extractPiece(text);
                    if (!piece) continue;

                    var key = String(sq.f) + ',' + String(sq.r);
                    placements[key] = piece;
                }
            }

            var out = [];
            for (var k in placements) {
                if (Object.prototype.hasOwnProperty.call(placements, k)) {
                    out.push(k + ':' + placements[k]);
                }
            }

            return {rawNodes: rawNodes, placements: out};
        })()
        """
        payload = self._run_js(js)
        if not payload or not isinstance(payload, dict):
            print("[Vision] No pieces found — make sure you are in a chess.com game.")
            self._set_debug(
                status="no_pieces",
                raw_nodes=0,
                placed=0,
                message="No readable board payload from page",
            )
            return None

        placements = payload.get("placements", [])
        raw_nodes = int(payload.get("rawNodes", 0))
        if not placements:
            print("[Vision] No pieces found — make sure you are in a chess.com game.")
            self._set_debug(
                status="no_pieces",
                raw_nodes=raw_nodes,
                placed=0,
                message="No piece placements decoded from DOM",
            )
            return None

        board = [[""] * 8 for _ in range(8)]
        placed = 0

        for entry in placements:
            try:
                sq, piece_char = entry.split(":", 1)
                f_str, r_str = sq.split(",", 1)
                file_idx = int(f_str)
                rank_idx = int(r_str)
            except Exception:
                continue

            if file_idx < 0 or file_idx > 7 or rank_idx < 0 or rank_idx > 7:
                continue

            board[7 - rank_idx][file_idx] = piece_char
            placed += 1

        if placed == 0:
            print("[Vision] Piece-like nodes found, but could not decode square/piece mapping.")
            self._set_debug(
                status="decode_failed",
                raw_nodes=raw_nodes,
                placed=0,
                message="Could not decode piece/square mapping",
            )
            return None

        fen = self._to_fen(board)
        self._set_debug(
            status="ok",
            raw_nodes=raw_nodes,
            placed=placed,
            message="Board decoded",
            fen=fen,
        )
        return fen

    # ── Chrome DevTools Protocol (raw WebSocket, stdlib only) ─────────────────

    def _run_js(self, js: str):
        """Run JavaScript in the Chrome tab and return the result value."""
        import socket, struct, base64

        if not self._tab_ws_url:
            return None

        ws = self._tab_ws_url.replace("ws://", "")
        host_port, path = ws.split("/", 1)
        host, port = host_port.rsplit(":", 1)
        path = "/" + path

        sock = socket.create_connection((host, int(port)), timeout=10)

        # Handshake
        key = base64.b64encode(b"chesspy123456789").decode()
        sock.sendall((
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode())

        # Read until end of HTTP headers
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += sock.recv(1024)

        # Send CDP command
        cmd = json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": js, "returnByValue": True}
        }).encode()

        mk = b'\x37\x42\x11\x09'
        masked = bytes(b ^ mk[i % 4] for i, b in enumerate(cmd))
        n = len(cmd)
        if n < 126:
            sock.sendall(b'\x81' + bytes([0x80 | n]) + mk + masked)
        else:
            sock.sendall(b'\x81\xfe' + struct.pack("!H", n) + mk + masked)

        # Read response frame
        data = b""
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            data += chunk
            if len(data) < 2:
                continue
            lb = data[1] & 0x7F
            off = 2
            if lb == 126:
                if len(data) < 4: continue
                fl = struct.unpack("!H", data[2:4])[0]; off = 4
            elif lb == 127:
                if len(data) < 10: continue
                fl = struct.unpack("!Q", data[2:10])[0]; off = 10
            else:
                fl = lb
            if len(data) >= off + fl:
                frame = data[off:off+fl]
                break

        sock.close()

        try:
            resp = json.loads(frame.decode())
            val = resp.get("result", {}).get("result", {})
            return val.get("value")
        except Exception:
            return None

    def _to_fen(self, board) -> str:
        ranks = []
        for row in board:
            s, empty = "", 0
            for p in row:
                if not p:
                    empty += 1
                else:
                    if empty: s += str(empty); empty = 0
                    s += p
            if empty: s += str(empty)
            ranks.append(s)
        # Detect turn from board (simplified — defaults to white)
        return "/".join(ranks) + " w KQkq - 0 1"