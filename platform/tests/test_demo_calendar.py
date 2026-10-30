import importlib
import sys
import xml.etree.ElementTree as ET

import pytest


NATURAL_LANGUAGE_TITLE = (
    "Design Night on September 19, 2026 from 7 PM to 8 PM"
)


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("QUNKONG_STATE_DIR", str(tmp_path / "state"))
    for name in ("backend.demo", "backend.demo_invitation", "backend.service"):
        sys.modules.pop(name, None)
    return importlib.import_module("backend.demo")


def calendar_editor(*, suggestion_count=1):
    root = ET.Element("Application", width="440", height="956")
    ET.SubElement(
        root,
        "XCUIElementTypeTextField",
        type="XCUIElementTypeTextField",
        name="title-field",
        value=NATURAL_LANGUAGE_TITLE,
    )
    for index in range(suggestion_count):
        cell = ET.SubElement(
            root,
            "XCUIElementTypeCell",
            type="XCUIElementTypeCell",
            enabled="true",
            x=str(20 + index),
            y="249",
            width="400",
            height="61",
        )
        ET.SubElement(
            cell,
            "XCUIElementTypeStaticText",
            type="XCUIElementTypeStaticText",
            enabled="true",
            name="Design Night",
            label="Design Night",
        )
    return root


def test_ios26_calendar_suggestion_uses_unique_title_cell(demo):
    x, y = demo.calendar_suggestion_point(
        calendar_editor(),
        natural_language_title=NATURAL_LANGUAGE_TITLE,
        event_title="Design Night",
    )

    assert x == pytest.approx((20 + 400 / 2) / 440)
    assert y == pytest.approx((249 + 61 / 2) / 956)


def test_calendar_suggestion_rejects_ambiguous_title_cells(demo):
    with pytest.raises(RuntimeError, match="suggestion is not uniquely visible"):
        demo.calendar_suggestion_point(
            calendar_editor(suggestion_count=2),
            natural_language_title=NATURAL_LANGUAGE_TITLE,
            event_title="Design Night",
        )


@pytest.mark.parametrize(
    ("start", "end"),
    (
        ("Starts, 7:00\u202fPM, Sep 19, 2026", "Ends, 8:00\u202fPM, Sep 19, 2026"),
        ("Starts, 19:00, Sep 19, 2026", "Ends, 20:00, Sep 19, 2026"),
    ),
)
def test_calendar_editor_accepts_equivalent_12_or_24_hour_times(demo, start, end):
    root = ET.Element("Application")
    ET.SubElement(root, "Cell", name="start-date-picker-cell", label=start)
    ET.SubElement(root, "Cell", name="end-date-picker-cell", label=end)

    assert demo.calendar_editor_has_expected_time(root) is True


def test_calendar_editor_rejects_wrong_date(demo):
    root = ET.Element("Application")
    ET.SubElement(
        root,
        "Cell",
        name="start-date-picker-cell",
        label="Starts, 7:00 PM, Sep 20, 2026",
    )
    ET.SubElement(
        root,
        "Cell",
        name="end-date-picker-cell",
        label="Ends, 8:00 PM, Sep 20, 2026",
    )

    assert demo.calendar_editor_has_expected_time(root) is False


@pytest.mark.parametrize(
    "event_label",
    (
        "Design Night, from 7:00\u202fPM to 8:00\u202fPM, Demo Calendar",
        "Design Night, Ferry Building, from 7:00\u202fPM to 8:00\u202fPM, Demo Calendar",
        "Design Night, from 19:00 to 20:00, Demo Calendar",
    ),
)
def test_calendar_details_accept_equivalent_12_or_24_hour_times(demo, event_label):
    root = ET.Element("Application")
    ET.SubElement(
        root,
        "StaticText",
        name="event-details-title-text",
        value="Design Night",
    )
    ET.SubElement(
        root,
        "TextView",
        type="XCUIElementTypeTextView",
        value="Ferry Building\n1 Ferry Building, San Francisco, CA 94111",
    )
    ET.SubElement(
        root,
        "TextView",
        type="XCUIElementTypeTextView",
        value="Ferry Building\n1 Ferry Building, San Francisco, CA 94111",
    )
    ET.SubElement(root, "StaticText", name="Saturday, Sep 19, 2026")
    ET.SubElement(
        root,
        "Other",
        name="event-shown:Design Night",
        label=event_label,
    )
    ET.SubElement(root, "Cell", name="alert-cell", value="1 hour before")

    assert demo.calendar_details_match(root) is True


def test_calendar_details_reject_wrong_end_time(demo):
    root = ET.Element("Application")
    ET.SubElement(
        root,
        "StaticText",
        name="event-details-title-text",
        value="Design Night",
    )
    ET.SubElement(
        root,
        "TextView",
        type="XCUIElementTypeTextView",
        value="Ferry Building",
    )
    ET.SubElement(root, "StaticText", name="Saturday, Sep 19, 2026")
    ET.SubElement(
        root,
        "Other",
        name="event-shown:Design Night",
        label="Design Night, from 7:00 PM to 9:00 PM, Demo Calendar",
    )
    ET.SubElement(root, "Cell", name="alert-cell", value="1 hour before")

    assert demo.calendar_details_match(root) is False
