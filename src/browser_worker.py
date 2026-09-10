"""Playwright Chromium worker managing hardware-accelerated WebGL 2.0 evaluation."""

import asyncio
import http.server
import logging
import os
import socketserver
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright, Browser, Page

from .config import (
    EVALUATOR_PORT,
    BENCHMARK_RESOLUTION_WIDTH,
    BENCHMARK_RESOLUTION_HEIGHT,
    EVALUATOR_WEB_DIR,
    PLAYWRIGHT_CHANNEL
)

logger = logging.getLogger(__name__)


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress HTTP server noise logs


class LocalHTTPServer:
    """Threaded local HTTP server serving evaluator_web assets."""
    def __init__(self, directory: Path, port: int = EVALUATOR_PORT):
        self.directory = str(directory)
        self.port = port
        self.httpd: Optional[socketserver.TCPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        handler = lambda *args, **kwargs: QuietHTTPRequestHandler(*args, directory=self.directory, **kwargs)
        socketserver.TCPServer.allow_reuse_address = True
        try:
            self.httpd = socketserver.TCPServer(("127.0.0.1", self.port), handler)
        except OSError:
            self.httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
            self.port = self.httpd.server_address[1]

        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"Local evaluator HTTP server serving {self.directory} at http://127.0.0.1:{self.port}")

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            logger.info("Local evaluator HTTP server stopped")


class BrowserEvaluatorWorker:
    """Persistent Playwright browser worker evaluating shaders in WebGL2 context."""
    def __init__(
        self,
        port: int = EVALUATOR_PORT,
        headless: bool = True,
        width: int = BENCHMARK_RESOLUTION_WIDTH,
        height: int = BENCHMARK_RESOLUTION_HEIGHT
    ):
        self.port = port
        self.headless = headless
        self.width = width
        self.height = height

        self.server: Optional[LocalHTTPServer] = None
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.preflight_info: Dict[str, Any] = {}

    async def start(self) -> Dict[str, Any]:
        """Starts HTTP server and launches persistent Playwright Chromium browser."""
        self.server = LocalHTTPServer(EVALUATOR_WEB_DIR, self.port)
        self.server.start()
        self.port = self.server.port

        self.playwright = await async_playwright().start()

        # Launch Chromium with hardware WebGL2 flags
        launch_args = [
            "--enable-webgl",
            "--ignore-gpu-blocklist",
            "--use-gl=angle",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding"
        ]

        try:
            # First try configured channel (e.g. "chrome")
            self.browser = await self.playwright.chromium.launch(
                channel=PLAYWRIGHT_CHANNEL,
                headless=self.headless,
                args=launch_args
            )
        except Exception as e:
            logger.warning(f"Failed to launch with channel '{PLAYWRIGHT_CHANNEL}': {e}. Falling back to default chromium.")
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=launch_args
            )

        context = await self.browser.new_context(
            viewport={"width": self.width, "height": self.height},
            device_scale_factor=1.0
        )

        self.page = await context.new_page()
        evaluator_url = f"http://127.0.0.1:{self.port}/index.html"
        await self.page.goto(evaluator_url)
        await self.page.wait_for_load_state("networkidle")

        self.preflight_info = await self.page.evaluate("window.checkPreflight()")
        logger.info(f"WebGL2 Evaluator Initialized: {self.preflight_info}")
        return self.preflight_info

    async def evaluate_shader(
        self,
        glsl_code: str,
        sample_times: List[float],
        warmup_frames: int = 25,
        timed_samples: int = 10,
        channel_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Evaluates candidate shader in Playwright page using WebGL2 and timer query."""
        if not self.page:
            raise RuntimeError("Browser worker is not started")

        options = {
            "code": glsl_code,
            "sampleTimes": sample_times,
            "warmupFrames": warmup_frames,
            "timedSamples": timed_samples,
            "channelTypes": channel_types or ["2d", "2d", "2d", "2d"]
        }

        result = await self.page.evaluate("(options) => window.evaluateShader(options)", options)
        return result

    async def stop(self):
        """Cleanly closes browser and stops local HTTP server."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        if self.server:
            self.server.stop()
        logger.info("BrowserEvaluatorWorker terminated")
