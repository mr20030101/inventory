"""Runs the SAIMS API inside the desktop app, for demos, single-PC use and small-network sharing.

By default the server listens on 127.0.0.1 only. With `share=True` it listens on every network interface over
HTTPS, using a certificate this computer creates for itself (see saims/tls.py), so other computers on the local
network can sign in to the same data. For a larger school, run the server separately (python -m saims.backend)
on PostgreSQL.
"""
from __future__ import annotations

import errno
import socket
import ssl
import threading
import time

import uvicorn

from saims import tls
from saims.backend.config import Settings
from saims.backend.main import create_app
from saims.paths import data_dir


class LocalServer:
    def __init__(self, seed_demo: bool = True, share: bool = False, port: int = tls.DEFAULT_PORT):
        self.seed_demo, self.share = seed_demo, share
        self.port = port if share else 0
        self.cert_pem = ""
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"{'https' if self.share else 'http'}://127.0.0.1:{self.port}"

    @property
    def verify(self) -> ssl.SSLContext | bool:
        """How this computer's own client checks the server: the pinned certificate when sharing."""
        return tls.pinned_context(self.cert_pem) if self.share else True

    @property
    def security_code(self) -> str:
        return tls.short_code(self.cert_pem) if self.cert_pem else ""

    def start(self, timeout: float = 60.0) -> str:
        host = "0.0.0.0" if self.share else "127.0.0.1"
        extra = {}
        if self.share:
            cert, key = tls.ensure_certificate(data_dir() / "tls", f"SAIMS on {socket.gethostname()}")
            self.cert_pem = cert.read_text(encoding="ascii")
            extra = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
        with socket.socket() as s:  # find a free port, or check the chosen one is free
            if self.share:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, self.port))
            except OSError as exc:
                if exc.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)):
                    raise RuntimeError(f"Port {self.port} is already in use on this computer. "
                                       "Choose another port.") from None
                raise
            self.port = s.getsockname()[1]
        app = create_app(Settings(seed_demo_data=self.seed_demo))
        # log_config=None: uvicorn's console logging probes sys.stdout, which does not exist in the windowed Windows
        # app (it fails with "Unable to configure formatter 'default'"). SAIMS logs to a file instead.
        config = uvicorn.Config(app, host=host, port=self.port, log_level="warning", access_log=False,
                                log_config=None, **extra)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="saims-server", daemon=True)
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("The built-in SAIMS server did not start.")
            time.sleep(0.05)
        return self.url

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
        self._server = self._thread = None
