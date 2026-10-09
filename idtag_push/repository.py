import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg


@dataclass
class Delivery:
    id: UUID
    device_id: UUID | None
    platform: str
    token: str


@dataclass
class QueuedNotification:
    id: UUID
    title: str
    body: str
    data: dict[str, Any]
    attempts: int
    deliveries: list[Delivery]


class Repository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def register_device(
        self, community_code: str, card_number: str, platform: str, token: str
    ) -> UUID:
        row = await self.pool.fetchrow(
            """
            INSERT INTO devices (community_code, card_number, platform, push_token)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (platform, push_token) DO UPDATE SET
                community_code = EXCLUDED.community_code,
                card_number = EXCLUDED.card_number,
                active = TRUE,
                updated_at = NOW(),
                last_seen_at = NOW()
            RETURNING id
            """,
            community_code, card_number, platform, token,
        )
        return row["id"]

    async def unregister_device(self, platform: str, token: str) -> bool:
        result = await self.pool.execute(
            "DELETE FROM devices WHERE platform = $1 AND push_token = $2", platform, token
        )
        return result != "DELETE 0"

    async def enqueue(
        self,
        community_code: str,
        card_number: str,
        title: str,
        body: str,
        data: dict[str, Any],
    ) -> tuple[UUID, int]:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                notification_id = await connection.fetchval(
                    """
                    INSERT INTO notifications (community_code, card_number, title, body, data)
                    VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id
                    """,
                    community_code, card_number, title, body, json.dumps(data),
                )
                result = await connection.execute(
                    """
                    INSERT INTO deliveries (notification_id, device_id, platform, token_snapshot)
                    SELECT $1, id, platform, push_token
                    FROM devices
                    WHERE community_code = $2 AND card_number = $3 AND active = TRUE
                    """,
                    notification_id, community_code, card_number,
                )
                count = int(result.split()[-1])
                if count == 0:
                    await connection.execute("DELETE FROM notifications WHERE id = $1", notification_id)
                    raise LookupError("no active devices found for community_code and card_number")
                return notification_id, count

    async def claim_next(self) -> QueuedNotification | None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT * FROM notifications
                    WHERE (status = 'pending' AND next_attempt_at <= NOW())
                       OR (status = 'processing' AND locked_at < NOW() - INTERVAL '5 minutes')
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED LIMIT 1
                    """
                )
                if not row:
                    return None
                await connection.execute(
                    "UPDATE notifications SET status='processing', locked_at=NOW(), attempts=attempts+1 WHERE id=$1",
                    row["id"],
                )
                deliveries = await connection.fetch(
                    """
                    SELECT id, device_id, platform, token_snapshot FROM deliveries
                    WHERE notification_id=$1 AND status='pending'
                    """,
                    row["id"],
                )
        raw_data = row["data"]
        data = json.loads(raw_data) if isinstance(raw_data, str) else dict(raw_data)
        return QueuedNotification(
            id=row["id"],
            title=row["title"],
            body=row["body"],
            data=data,
            attempts=row["attempts"] + 1,
            deliveries=[
                Delivery(d["id"], d["device_id"], d["platform"], d["token_snapshot"])
                for d in deliveries
            ],
        )

    async def mark_accepted(self, delivery_id: UUID, provider_id: str | None) -> None:
        await self.pool.execute(
            """
            UPDATE deliveries SET status='accepted', provider_message_id=$2,
                last_error=NULL, updated_at=NOW() WHERE id=$1
            """,
            delivery_id,
            provider_id,
        )

    async def mark_invalid(self, delivery: Delivery, error: str) -> None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE deliveries SET status='invalid', last_error=$2, updated_at=NOW() WHERE id=$1",
                    delivery.id, error,
                )
                if delivery.device_id:
                    await connection.execute(
                        "DELETE FROM devices WHERE id=$1 AND push_token=$2", delivery.device_id, delivery.token
                    )

    async def mark_retry_error(self, delivery_id: UUID, error: str) -> None:
        await self.pool.execute(
            "UPDATE deliveries SET last_error=$2, updated_at=NOW() WHERE id=$1", delivery_id, error[:2000]
        )

    async def finish_or_retry(self, notification_id: UUID, attempts: int, max_attempts: int) -> None:
        pending = await self.pool.fetchval(
            "SELECT COUNT(*) FROM deliveries WHERE notification_id=$1 AND status='pending'", notification_id
        )
        if pending == 0:
            await self.pool.execute("DELETE FROM notifications WHERE id=$1", notification_id)
        elif attempts >= max_attempts:
            await self.pool.execute(
                "UPDATE notifications SET status='failed', locked_at=NULL WHERE id=$1",
                notification_id,
            )
        else:
            delay = min(3600, 2 ** attempts)
            await self.pool.execute(
                """
                UPDATE notifications SET status='pending',
                    next_attempt_at=NOW()+($2 * INTERVAL '1 second'), locked_at=NULL
                WHERE id=$1
                """,
                notification_id, delay,
            )
