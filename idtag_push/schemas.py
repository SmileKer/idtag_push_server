from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DeviceRegistration(BaseModel):
    community_code: str = Field(min_length=1, max_length=64)
    card_number: str = Field(min_length=1, max_length=128)
    platform: Literal["ios", "android"]
    push_token: str = Field(min_length=16, max_length=4096)

    @field_validator("community_code", "card_number")
    @classmethod
    def normalize_routing_key(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("push_token")
    @classmethod
    def strip_token(cls, value: str) -> str:
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
    community_code: str = Field(min_length=1, max_length=64)
    card_number: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4096)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("community_code", "card_number")
    @classmethod
    def normalize_routing_key(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("title", "body")
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
