import asyncio
import json
from uuid import uuid4

import pytest

from idtag_push.socket_server import SocketServer


@pytest.mark.asyncio
async def test_socket_protocol_accepts_authenticated_json_line():
    expected_id = uuid4()

    async def enqueue(card_number, title, body, data):
        assert (card_number, title, body, data) == ("C001", "Hello", "World", {"screen": "home"})
        return expected_id, 2

    server = SocketServer("127.0.0.1", 0, "s" * 16, enqueue)
    await server.start()
    port = server.server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    request = {
        "secret": "s" * 16,
        "card_number": "C001",
        "title": "Hello",
        "body": "World",
        "data": {"screen": "home"},
    }
    writer.write(json.dumps(request).encode() + b"\n")
    await writer.drain()
    response = json.loads(await reader.readline())
    writer.close()
    await writer.wait_closed()
    await server.close()

    assert response == {"ok": True, "notification_id": str(expected_id), "target_count": 2}
