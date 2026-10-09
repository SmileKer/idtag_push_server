import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import google.auth.transport.requests
import httpx
import jwt
from google.oauth2 import service_account


@dataclass(frozen=True)
class SendResult:
    accepted: bool
    invalid_token: bool = False
    retryable: bool = False
    provider_id: str | None = None
    error: str | None = None


class FCMProvider:
    def __init__(self, project_id: str, credentials_file: Path, client: httpx.AsyncClient) -> None:
        self.project_id = project_id
        self.client = client
        self.credentials = service_account.Credentials.from_service_account_file(
            str(credentials_file), scopes=["https://www.googleapis.com/auth/firebase.messaging"]
        )

    async def _access_token(self) -> str:
        def refresh() -> str:
            self.credentials.refresh(google.auth.transport.requests.Request())
            return str(self.credentials.token)

        return await asyncio.to_thread(refresh)

    async def send(self, token: str, title: str, body: str, data: dict[str, Any]) -> SendResult:
        access_token = await self._access_token()
        string_data = {
            str(k): (
                v
                if isinstance(v, str)
                else json.dumps(v, ensure_ascii=False, separators=(",", ":"))
            )
            for k, v in data.items()
        }
        response = await self.client.post(
            f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "message": {
                    "token": token,
                    "notification": {"title": title, "body": body},
                    "data": string_data,
                }
            },
        )
        payload = response.json()
        if response.is_success:
            return SendResult(True, provider_id=payload.get("name"))
        error = payload.get("error", {})
        status = error.get("status", "")
        detail_codes = {
            detail.get("errorCode")
            for detail in error.get("details", [])
            if isinstance(detail, dict)
        }
        invalid = status == "UNREGISTERED" or bool(
            {"UNREGISTERED", "INVALID_ARGUMENT"} & detail_codes
        )
        retryable = response.status_code in {429, 500, 502, 503, 504}
        return SendResult(False, invalid_token=invalid, retryable=retryable, error=str(payload))


class APNSProvider:
    def __init__(
        self,
        team_id: str,
        key_id: str,
        key_file: Path,
        topic: str,
        sandbox: bool,
        client: httpx.AsyncClient,
    ) -> None:
        self.team_id, self.key_id, self.topic, self.client = team_id, key_id, topic, client
        self.private_key = key_file.read_text()
        self.base_url = "https://api.sandbox.push.apple.com" if sandbox else "https://api.push.apple.com"
        self._jwt: tuple[str, float] | None = None

    def _authorization_token(self) -> str:
        now = time.time()
        if not self._jwt or now - self._jwt[1] > 3000:
            token = jwt.encode(
                {"iss": self.team_id, "iat": int(now)},
                self.private_key,
                algorithm="ES256",
                headers={"kid": self.key_id},
            )
            self._jwt = (token, now)
        return self._jwt[0]

    async def send(self, token: str, title: str, body: str, data: dict[str, Any]) -> SendResult:
        response = await self.client.post(
            f"{self.base_url}/3/device/{token}",
            headers={
                "authorization": f"bearer {self._authorization_token()}",
                "apns-topic": self.topic,
                "apns-push-type": "alert",
                "apns-priority": "10",
            },
            json={**data, "aps": {"alert": {"title": title, "body": body}, "sound": "default"}},
        )
        if response.is_success:
            return SendResult(True, provider_id=response.headers.get("apns-id"))
        try:
            reason = response.json().get("reason", response.text)
        except ValueError:
            reason = response.text
        invalid = reason in {"BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"}
        retryable = response.status_code in {429, 500, 503}
        return SendResult(False, invalid_token=invalid, retryable=retryable, error=str(reason))


class DryRunProvider:
    async def send(self, token: str, title: str, body: str, data: dict[str, Any]) -> SendResult:
        return SendResult(True, provider_id=f"dry-run:{token[-8:]}")


class UnavailableProvider:
    def __init__(self, platform: str) -> None:
        self.platform = platform

    async def send(self, token: str, title: str, body: str, data: dict[str, Any]) -> SendResult:
        return SendResult(
            False,
            retryable=False,
            error=f"{self.platform} push provider is not configured",
        )
