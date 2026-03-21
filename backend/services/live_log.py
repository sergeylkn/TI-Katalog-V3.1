"""
Live log broadcaster — SSE (Server-Sent Events).
Компоненти підписуються на події і отримують їх в реальному часі.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Set, AsyncGenerator

class LiveLogBus:
    """In-process pub/sub для live логів."""
    def __init__(self):
        self._queues: Set[asyncio.Queue] = set()

    def push(self, event: dict):
        """Відправити подію всім підписникам."""
        event.setdefault("ts", datetime.now(timezone.utc).strftime("%H:%M:%S"))
        dead = set()
        for q in self._queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.add(q)
        for q in dead:
            self._queues.discard(q)

    async def subscribe(self) -> "asyncio.Queue":
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._queues.discard(q)

    async def stream(self) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted strings."""
        q = await self.subscribe()
        try:
            # Send connected ping
            yield f"data: {json.dumps({'type':'connected','msg':'Live log connected'})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\":\"ping\"}\n\n"  # keep-alive
        finally:
            self.unsubscribe(q)

# Global singleton
bus = LiveLogBus()


def log(msg: str, level: str = "info", doc: str = "", extra: dict = None):
    """Shortcut to push a log event."""
    event = {"type": "log", "level": level, "msg": msg, "doc": doc}
    if extra:
        event.update(extra)
    bus.push(event)


def progress(done: int, total: int, current_doc: str = "", products_found: int = 0):
    """Push progress update."""
    bus.push({
        "type": "progress",
        "done": done, "total": total,
        "pct": round(done / total * 100) if total else 0,
        "current": current_doc,
        "products": products_found,
    })
