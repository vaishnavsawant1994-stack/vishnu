from devices.tools import register_virtual_device_tools
from devices.virtual_lab import VirtualDeviceLab
from tools.registry import Risk


class Registry:
    def __init__(self):
        self.tools = []

    def register(self, tool):
        self.tools.append(tool)


def test_virtual_device_actions_are_registered_as_bounded_governed_tools():
    lab = VirtualDeviceLab()
    device = lab.create_device("Desktop Fixture", "desktop")
    registry = Registry()

    register_virtual_device_tools(registry, lab)

    by_name = {tool.name: tool for tool in registry.tools}
    assert set(by_name) == {"virtual_device_status", "virtual_device_execute"}
    assert by_name["virtual_device_status"].risk == Risk.READ_ONLY
    assert by_name["virtual_device_execute"].risk == Risk.REVERSIBLE
    assert by_name["virtual_device_execute"].verification_required is True
    assert by_name["virtual_device_execute"].input_schema["additionalProperties"] is False

    result = by_name["virtual_device_execute"].handler(
        {
            "device_id": device.device_id,
            "action": "device.status",
            "parameters": {},
            "request_id": "tool-req-1",
        }
    )
    verification = by_name["virtual_device_execute"].verifier(
        {"device_id": device.device_id},
        result,
    )

    assert result["simulated"] is True
    assert verification.verified is True
    assert verification.evidence == {"request_id": "tool-req-1", "mode": "simulated"}
