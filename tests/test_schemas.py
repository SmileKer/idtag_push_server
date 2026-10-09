import pytest
from pydantic import ValidationError

from idtag_push.schemas import DeviceRegistration, PushRequest


def test_device_registration_strips_values():
    value = DeviceRegistration(
        community_code="  north_01  ",
        card_number="  a123  ",
        platform="ios",
        push_token="  abcdefghijklmnop  ",
    )
    assert value.community_code == "NORTH_01"
    assert value.card_number == "A123"
    assert value.push_token == "abcdefghijklmnop"


def test_push_rejects_blank_title():
    with pytest.raises(ValidationError):
        PushRequest(community_code="NORTH_01", card_number="A123", title="  ", body="message")
