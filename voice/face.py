"""Push robot state to the iced face window over a unix socket.

The face (Rust/iced) binds the socket and listens; we connect as a client and
send newline-delimited JSON snapshots. Best-effort: if the face isn't running
the calls are silent no-ops and we retry connecting on the next update, so the
voice loop never blocks on the GUI.

Protocol (partial updates, the face merges them):
  {"busy": true}                  -> thinking (face shows the thinking emoji)
  {"busy": false, "emoji": "😎"}  -> idle with an expression
  {"heard": "..."}                -> subtitle line 1 (what it heard)
  {"saying": "..."}               -> subtitle line 2 (what it's saying)
"""
from __future__ import annotations

import json
import re
import socket
import threading

# Emoji + variation selectors + regional indicators. Good enough to split a
# leading expression emoji out of a spoken reply so TTS doesn't try to say it.
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002190-\U000021FF"
    "\U0001F1E6-\U0001F1FF\U0000FE00-\U0000FE0F\U00002B00-\U00002BFF\U00002700-\U000027BF]+"
)


def split_emoji(text: str) -> tuple[str, str | None]:
    """Return (text without emoji, first emoji found or None)."""
    found = EMOJI_RE.findall(text)
    emoji = None
    if found:
        # first single codepoint that isn't a bare variation selector
        for ch in "".join(found):
            if ch >= "\U0001F000" or "\U00002600" <= ch <= "\U000027BF" or "\U00002B00" <= ch <= "\U00002BFF":
                emoji = ch
                break
    clean = EMOJI_RE.sub("", text).strip()
    return clean, emoji


class Face:
    """Thread-safe best-effort client. Use Face(None) for a no-op."""

    def __init__(self, path: str | None):
        self.path = path
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    def _connect(self):
        if not self.path:
            return
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(self.path)
            self._sock = s
        except OSError:
            self._sock = None

    def _send(self, **kw):
        if not self.path:
            return
        with self._lock:
            if self._sock is None:
                self._connect()
            if self._sock is None:
                return
            try:
                self._sock.sendall((json.dumps(kw) + "\n").encode())
            except OSError:
                self._sock = None

    def busy(self, b: bool):
        self._send(busy=b)

    def heard(self, text: str):
        self._send(heard=text)

    def saying(self, text: str):
        self._send(saying=text)

    def emoji(self, e: str):
        self._send(emoji=e)
