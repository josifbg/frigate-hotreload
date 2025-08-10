from __future__ import annotations
from typing import List
from fastapi import WebSocket

class WSBus:
    def __init__(self):
        self.clients: List[WebSocket] = []

    async def register(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)

    async def unregister(self, ws: WebSocket):
        if ws in self.clients:
            self.clients.remove(ws)

    async def broadcast(self, payload):
        stale = []
        for c in self.clients:
            try:
                await c.send_json(payload)
            except Exception:
                stale.append(c)
        for s in stale:
            await self.unregister(s)
