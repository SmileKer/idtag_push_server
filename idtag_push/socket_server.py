import asyncio
import hmac
import json
import logging
from collections.abc import Awaitable, Callable

from pydantic import ValidationError

from .schemas import SocketPushRequest

logger = logging.getLogger(__name__)
MAX_LINE_BYTES = 64 * 1024


class SocketServer:
    def __init__(
        self,
        host: str,
        port: int,
        secret: str,
        enqueue: Callable[..., Awaitable[tuple[object, int]]],
    ) -> None:
        self.host, self.port, self.secret, self.enqueue = host, port, secret, enqueue
        self.server: asyncio.Server | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, self.host, self.port, limit=MAX_LINE_BYTES + 1)

    async def close(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                if len(line) > MAX_LINE_BYTES:
                    await self._reply(writer, {"ok": False, "error": "request too large"})
                    break
                try:
                    request = SocketPushRequest.model_validate_json(line)
                    if not hmac.compare_digest(request.secret, self.secret):
                        await self._reply(writer, {"ok": False, "error": "unauthorized"})
                        continue
                    notification_id, count = await self.enqueue(
                        request.card_number, request.title, request.body, request.data
                    )
                    await self._reply(
                        writer,
                        {
                            "ok": True,
                            "notification_id": str(notification_id),
                            "target_count": count,
                        },
                    )
                except (ValidationError, json.JSONDecodeError) as exc:
                    await self._reply(writer, {"ok": False, "error": "invalid request", "detail": str(exc)})
                except LookupError as exc:
                    await self._reply(writer, {"ok": False, "error": str(exc)})
                except Exception:
                    logger.exception("socket request failed from %s", peer)
                    await self._reply(writer, {"ok": False, "error": "internal error"})
        finally:
            writer.close()
            await writer.wait_closed()

    @staticmethod
    async def _reply(writer: asyncio.StreamWriter, payload: dict[str, object]) -> None:
        writer.write(json.dumps(payload, ensure_ascii=False).encode() + b"\n")
        await writer.drain()
