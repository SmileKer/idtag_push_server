import pytest
from pydantic import ValidationError

from idtag_push.schemas import DeviceRegistration, PushRequest


def test_device_registration_strips_values():
    value = DeviceRegistration(card_number="  A123  ", platform="ios", push_token="  abcdefghijklmnop  ")
    assert value.card_number == "A123"
    assert value.push_token == "abcdefghijklmnop"


def test_push_rejects_blank_title():
    with pytest.raises(ValidationError):
        PushRequest(card_number="A123", title="  ", body="message")
