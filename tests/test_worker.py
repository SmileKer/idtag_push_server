from uuid import uuid4

import pytest

from idtag_push.providers import SendResult, UnavailableProvider
from idtag_push.repository import Delivery, QueuedNotification
from idtag_push.worker import PushWorker


class FakeRepository:
    def __init__(self, job):
        self.job = job
        self.accepted = []
        self.invalid = []
        self.finished = []

    async def claim_next(self):
        job, self.job = self.job, None
        return job

    async def mark_accepted(self, delivery_id, provider_id):
        self.accepted.append((delivery_id, provider_id))

    async def mark_invalid(self, delivery, error):
        self.invalid.append((delivery, error))

    async def mark_retry_error(self, delivery_id, error):
        raise AssertionError(f"unexpected retry: {delivery_id} {error}")

    async def finish_or_retry(self, notification_id, attempts, max_attempts):
        self.finished.append((notification_id, attempts, max_attempts))


class Provider:
    def __init__(self, result):
        self.result = result

    async def send(self, *_args):
        return self.result


@pytest.mark.asyncio
async def test_worker_marks_provider_acceptance_and_finishes():
    delivery = Delivery(uuid4(), uuid4(), "ios", "a" * 64)
    job = QueuedNotification(uuid4(), "title", "body", {}, 1, [delivery])
    repository = FakeRepository(job)
    worker = PushWorker(repository, {"ios": Provider(SendResult(True, provider_id="provider-1"))}, 0.01, 8)

    async def finish_once(*args):
        await FakeRepository.finish_or_retry(repository, *args)
        worker.stop()

    repository.finish_or_retry = finish_once
    await worker.run()

    assert repository.accepted == [(delivery.id, "provider-1")]
    assert repository.finished == [(job.id, 1, 8)]


@pytest.mark.asyncio
async def test_worker_removes_invalid_token_via_repository():
    delivery = Delivery(uuid4(), uuid4(), "android", "b" * 64)
    job = QueuedNotification(uuid4(), "title", "body", {}, 1, [delivery])
    repository = FakeRepository(job)
    worker = PushWorker(
        repository,
        {"android": Provider(SendResult(False, invalid_token=True, error="UNREGISTERED"))},
        0.01,
        8,
    )

    async def finish_once(*args):
        await FakeRepository.finish_or_retry(repository, *args)
        worker.stop()

    repository.finish_or_retry = finish_once
    await worker.run()
    assert repository.invalid == [(delivery, "UNREGISTERED")]


@pytest.mark.asyncio
async def test_unavailable_provider_returns_clear_error():
    result = await UnavailableProvider("APNs").send("token", "title", "body", {})

    assert result.accepted is False
    assert result.retryable is False
    assert result.error == "APNs push provider is not configured"
