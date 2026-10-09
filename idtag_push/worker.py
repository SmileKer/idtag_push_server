import asyncio
import logging
from typing import Any

from .providers import SendResult
from .repository import Repository

logger = logging.getLogger(__name__)


class PushWorker:
    def __init__(
        self,
        repository: Repository,
        providers: dict[str, Any],
        poll_seconds: float,
        max_attempts: int,
    ) -> None:
        self.repository = repository
        self.providers = providers
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                processed = await self._process_one()
            except Exception:
                logger.exception("worker iteration failed")
                processed = False
            if processed:
                continue
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass

    async def _process_one(self) -> bool:
        job = await self.repository.claim_next()
        if not job:
            return False
        for delivery in job.deliveries:
            try:
                result: SendResult = await self.providers[delivery.platform].send(
                    delivery.token, job.title, job.body, job.data
                )
            except Exception as exc:  # network/provider failures must not kill the worker
                logger.exception("push provider failure")
                await self.repository.mark_retry_error(delivery.id, str(exc))
                continue
            if result.accepted:
                await self.repository.mark_accepted(delivery.id, result.provider_id)
            elif result.invalid_token:
                await self.repository.mark_invalid(delivery, result.error or "invalid token")
            else:
                error = result.error or "provider rejected request"
                await self.repository.mark_retry_error(delivery.id, error)
        await self.repository.finish_or_retry(job.id, job.attempts, self.max_attempts)
        return True
