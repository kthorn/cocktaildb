import pytest
from pydantic import ValidationError
from api.models import requests


def test_group_models_contract():
    assert hasattr(requests, "GroupCreate")
    assert requests.GroupCreate(name="  Home  ").name == "Home"
    assert (
        requests.GroupJoin(invite_code=" ABCDEF123456 ").invite_code == "abcdef123456"
    )
    assert requests.GroupUpdate().model_dump(exclude_unset=True) == {}
    assert requests.GroupUpdate(description=None).model_dump(exclude_unset=True) == {
        "description": None
    }
    assert requests.GroupLeave(copy_inventory=True).copy_inventory is True


@pytest.mark.parametrize(
    "model,data",
    [
        ("GroupCreate", {"name": "  "}),
        ("GroupCreate", {"name": "a" * 101}),
        ("GroupCreate", {"name": "Home", "description": "a" * 501}),
        ("GroupUpdate", {"name": None}),
        ("GroupUpdate", {"name": " "}),
        ("GroupJoin", {"invite_code": "x" * 12}),
        ("GroupJoin", {"invite_code": "abcdef"}),
        ("GroupLeave", {}),
        ("GroupLeave", {"copy_inventory": "false"}),
    ],
)
def test_group_model_rejects_invalid_values(model, data):
    assert hasattr(requests, model)
    with pytest.raises(ValidationError):
        getattr(requests, model)(**data)
