import importlib
import json
import sys
import xml.etree.ElementTree as ET

import pytest


DUMMY_ADDRESS = "+14155550123"
FORMATTED_DUMMY_ADDRESS = "+1 (415) 555-0123"


@pytest.fixture
def invitation(tmp_path, monkeypatch):
    monkeypatch.setenv("PHONEUSE_STATE_DIR", str(tmp_path / "state"))
    sys.modules.pop("backend.demo_invitation", None)
    sys.modules.pop("backend.service", None)
    return importlib.import_module("backend.demo_invitation")


class MessagesPhone:
    def __init__(self, app, chip_label):
        self.app = app
        self.chip_label = chip_label

    def act(self, action, **params):
        assert action == "active_app"
        assert params == {}
        return {"bundleId": self.app}

    def tree(self):
        root = ET.Element("Application")
        to = ET.SubElement(
            root,
            "XCUIElementTypeTextField",
            name="To:",
            type="XCUIElementTypeTextField",
        )
        ET.SubElement(
            to,
            "XCUIElementTypeButton",
            type="XCUIElementTypeButton",
            label=self.chip_label,
        )
        ET.SubElement(
            root,
            "XCUIElementTypeTextView",
            name="messageBodyField",
            type="XCUIElementTypeTextView",
            value="",
            placeholderValue="iMessage",
        )
        return root


def write_recipient(invitation, **overrides):
    data = {
        "name": "Alex",
        "contact_name": "Taylor Example",
        "phone": DUMMY_ADDRESS,
    }
    data.update(overrides)
    path = invitation.service.STATE / "demo-recipient.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(0o600)


def test_configured_contact_matches_formatted_messages_chip(invitation):
    write_recipient(invitation)

    assert invitation.recipient() == ("Taylor Example", DUMMY_ADDRESS)
    phone = MessagesPhone(
        invitation.APP,
        f"Taylor Example, {FORMATTED_DUMMY_ADDRESS}",
    )

    _, _, is_imessage = invitation.inspect(
        phone,
        DUMMY_ADDRESS,
        contact_name="Taylor Example",
        require_image=False,
    )

    assert is_imessage is True


def test_recipient_keeps_public_persona_separate_from_contact(invitation):
    write_recipient(invitation, name="Taylor Example")

    with pytest.raises(RuntimeError, match="verified Messages contact"):
        invitation.recipient()


def test_wrong_chip_address_fails_without_leaking_addresses(invitation):
    phone = MessagesPhone(invitation.APP, "Taylor Example, +1 (415) 555-0199")

    with pytest.raises(RuntimeError) as error:
        invitation.inspect(
            phone,
            DUMMY_ADDRESS,
            contact_name="Taylor Example",
            require_image=False,
        )

    message = str(error.value)
    assert DUMMY_ADDRESS not in message
    assert "555-0199" not in message


def test_chip_suffix_cannot_hide_an_extra_recipient_label(invitation):
    phone = MessagesPhone(
        invitation.APP,
        f"Taylor Example, Work, {FORMATTED_DUMMY_ADDRESS}",
    )

    with pytest.raises(RuntimeError, match="exactly one recipient"):
        invitation.inspect(
            phone,
            DUMMY_ADDRESS,
            contact_name="Taylor Example",
            require_image=False,
        )


@pytest.mark.parametrize(
    "placeholder",
    (
        "",
        "iMessage",
        "Text Message",
        "Text Message • SMS",
        "Text Message • MMS",
        "Text Message • RCS",
    ),
)
def test_ios_transport_placeholders_are_empty_composers(invitation, placeholder):
    assert invitation.empty_composer(placeholder) is True


def test_contact_selection_failure_is_sanitized(invitation):
    class Cancel:
        def wait(self, seconds):
            return False

    class SelectionFailurePhone:
        cancel = Cancel()

        def act(self, action, **params):
            assert action == "text"

        def tree(self):
            raise RuntimeError(
                f"Expected screen item not found: Taylor Example, {DUMMY_ADDRESS}"
            )

    with pytest.raises(RuntimeError) as error:
        invitation.select_recipient(SelectionFailurePhone(), DUMMY_ADDRESS)

    assert str(error.value) == (
        "The configured recipient could not be selected. Nothing was sent."
    )
    assert "Taylor Example" not in str(error.value)
    assert DUMMY_ADDRESS not in str(error.value)


def test_recipient_selection_taps_the_unique_address_cell(invitation):
    class Cancel:
        def wait(self, seconds):
            return False

    class SuggestionPhone:
        cancel = Cancel()

        def __init__(self):
            self.actions = []

        def act(self, action, **params):
            self.actions.append((action, params))

        def tree(self):
            root = ET.Element("Application", width="440", height="956")
            cell = ET.SubElement(
                root,
                "XCUIElementTypeCell",
                type="XCUIElementTypeCell",
                enabled="true",
                x="296",
                y="119",
                width="141",
                height="134",
            )
            ET.SubElement(
                cell,
                "XCUIElementTypeStaticText",
                type="XCUIElementTypeStaticText",
                enabled="true",
                name=FORMATTED_DUMMY_ADDRESS,
                x="332",
                y="228",
                width="69",
                height="17",
            )
            return root

    phone = SuggestionPhone()

    invitation.select_recipient(phone, DUMMY_ADDRESS)

    assert phone.actions[0] == ("text", {"text": DUMMY_ADDRESS})
    action, point = phone.actions[1]
    assert action == "tap"
    assert point["x"] == pytest.approx((296 + 141 / 2) / 440)
    assert point["y"] == pytest.approx((119 + 134 / 2) / 956)


def test_recipient_selection_rejects_two_exact_address_cells_without_tapping(invitation):
    class Cancel:
        def wait(self, seconds):
            return False

    class AmbiguousSuggestionPhone:
        cancel = Cancel()

        def __init__(self):
            self.actions = []

        def act(self, action, **params):
            self.actions.append((action, params))

        def tree(self):
            root = ET.Element("Application", width="440", height="956")
            for y in (119, 263):
                cell = ET.SubElement(
                    root,
                    "XCUIElementTypeCell",
                    type="XCUIElementTypeCell",
                    enabled="true",
                    x="296",
                    y=str(y),
                    width="141",
                    height="134",
                )
                ET.SubElement(
                    cell,
                    "XCUIElementTypeStaticText",
                    type="XCUIElementTypeStaticText",
                    name=FORMATTED_DUMMY_ADDRESS,
                )
            return root

    phone = AmbiguousSuggestionPhone()

    with pytest.raises(RuntimeError) as error:
        invitation.select_recipient(phone, DUMMY_ADDRESS)

    assert str(error.value) == (
        "The configured recipient could not be selected. Nothing was sent."
    )
    assert phone.actions == [("text", {"text": DUMMY_ADDRESS})]


def message_state(invitation, *, outgoing=0, composer="", receipt=True, pending=False):
    root = ET.Element("Application", width="440", height="956")
    field = ET.SubElement(
        root,
        "XCUIElementTypeTextView",
        type="XCUIElementTypeTextView",
        name="messageBodyField",
        value=composer,
    )
    for _ in range(outgoing):
        ET.SubElement(
            root,
            "XCUIElementTypeStaticText",
            type="XCUIElementTypeStaticText",
            label=f"{invitation.MESSAGE}, You",
        )
    if receipt:
        ET.SubElement(
            root,
            "XCUIElementTypeStaticText",
            type="XCUIElementTypeStaticText",
            label="Delivered",
        )
    if pending:
        ET.SubElement(
            root,
            "XCUIElementTypeStaticText",
            type="XCUIElementTypeStaticText",
            label="Sending",
        )
    return root, field


class SendPhone:
    class Cancel:
        def wait(self, seconds):
            return False

    cancel = Cancel()

    def __init__(self, root, events, *, stop_after_first_observation=False):
        self.root = root
        self.events = events
        self.checks = 0
        self.stop_after_first_observation = stop_after_first_observation

    def act(self, action, **params):
        assert (action, params) == ("screenshot", {})
        return ""

    def click(self, name, kind=None):
        assert (name, kind) == ("sendButton", "Button")
        self.events.append("click")

    def check(self):
        self.checks += 1
        if self.stop_after_first_observation and self.checks > 1:
            raise RuntimeError("stop after proving the stale state was rejected")

    def tree(self):
        return self.root


@pytest.mark.parametrize(
    ("composer", "pending"),
    (
        ("\ufffc" + "draft is still present", True),
        ("", False),
    ),
)
def test_send_rejects_stale_bubble_and_receipt(invitation, monkeypatch, composer, pending):
    before_root, before_field = message_state(invitation, outgoing=1)
    after_root, _ = message_state(
        invitation,
        outgoing=1,
        composer=composer,
        pending=pending,
    )
    sample = bytes(48 * 28 * 3)
    events = []
    phone = SendPhone(after_root, events, stop_after_first_observation=True)
    monkeypatch.setattr(
        invitation,
        "inspect",
        lambda *args, **kwargs: (before_root, before_field, True),
    )
    monkeypatch.setattr(invitation, "draft_sample", lambda *args, **kwargs: sample)

    with pytest.raises(RuntimeError, match="stale state was rejected"):
        invitation.send(
            phone,
            "Taylor Example",
            DUMMY_ADDRESS,
            sample,
            lambda: events.append("before_send"),
        )

    assert events == ["before_send", "click"]


@pytest.mark.parametrize(
    ("composer", "pending"),
    (
        ("\ufffc" + "draft is still present", False),
        ("", True),
    ),
)
def test_send_waits_when_fresh_bubble_is_not_settled(invitation, monkeypatch, composer, pending):
    before_root, before_field = message_state(invitation, outgoing=1)
    after_root, _ = message_state(
        invitation,
        outgoing=2,
        composer=composer,
        pending=pending,
    )
    sample = bytes(48 * 28 * 3)
    events = []
    phone = SendPhone(after_root, events, stop_after_first_observation=True)
    monkeypatch.setattr(
        invitation,
        "inspect",
        lambda *args, **kwargs: (before_root, before_field, True),
    )
    monkeypatch.setattr(invitation, "draft_sample", lambda *args, **kwargs: sample)

    with pytest.raises(RuntimeError, match="stale state was rejected"):
        invitation.send(
            phone,
            "Taylor Example",
            DUMMY_ADDRESS,
            sample,
            lambda: events.append("before_send"),
        )

    assert events == ["before_send", "click"]


def test_send_accepts_only_a_new_outgoing_bubble_after_single_click(invitation, monkeypatch):
    before_root, before_field = message_state(invitation, outgoing=1)
    after_root, _ = message_state(invitation, outgoing=2)
    sample = bytes(48 * 28 * 3)
    events = []
    phone = SendPhone(after_root, events)
    monkeypatch.setattr(
        invitation,
        "inspect",
        lambda *args, **kwargs: (before_root, before_field, True),
    )
    monkeypatch.setattr(invitation, "draft_sample", lambda *args, **kwargs: sample)

    invitation.send(
        phone,
        "Taylor Example",
        DUMMY_ADDRESS,
        sample,
        lambda: events.append("before_send"),
    )

    assert events == ["before_send", "click"]
    assert phone.checks == 1


def test_send_accepts_stable_sms_without_a_delivery_receipt(invitation, monkeypatch):
    before_root, before_field = message_state(invitation, outgoing=0, receipt=False)
    after_root, _ = message_state(invitation, outgoing=1, receipt=False)
    sample = bytes(48 * 28 * 3)
    events = []
    phone = SendPhone(after_root, events)
    monkeypatch.setattr(
        invitation,
        "inspect",
        lambda *args, **kwargs: (before_root, before_field, False),
    )
    monkeypatch.setattr(invitation, "draft_sample", lambda *args, **kwargs: sample)

    invitation.send(
        phone,
        "Taylor Example",
        DUMMY_ADDRESS,
        sample,
        lambda: events.append("before_send"),
    )

    assert events == ["before_send", "click"]
    assert phone.checks == 6
