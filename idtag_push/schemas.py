from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DeviceRegistration(BaseModel):
    card_number: str = Field(min_length=1, max_length=128)
    platform: Literal["ios", "android"]
    push_token: str = Field(min_length=16, max_length=4096)

    @field_validator("card_number", "push_token")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class DeviceRegistrationResponse(BaseModel):
    device_id: UUID


class DeviceUnregister(BaseModel):
    platform: Literal["ios", "android"]
    push_token: str = Field(min_length=16, max_length=4096)


class PushRequest(BaseModel):
    card_number: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4096)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("card_number", "title", "body")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SocketPushRequest(PushRequest):
    secret: str = Field(min_length=16)


class PushResponse(BaseModel):
    notification_id: UUID
    target_count: int
