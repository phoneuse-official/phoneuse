import importlib
import sys
import xml.etree.ElementTree as ET

import pytest


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("PHONEUSE_STATE_DIR", str(tmp_path / "state"))
    for name in ("backend.demo", "backend.demo_invitation", "backend.service"):
        sys.modules.pop(name, None)
    return importlib.import_module("backend.demo")


def google_maps_place(*, query="Ferry Building San Francisco", place="Ferry Building"):
    root = ET.Element("Application", width="440", height="956")
    ET.SubElement(
        root,
        "XCUIElementTypeTextField",
        type="XCUIElementTypeTextField",
        name="SearchHeaderSearchTxtView",
        value=query,
        enabled="true",
    )
    card = ET.SubElement(
        root,
        "XCUIElementTypeOther",
        type="XCUIElementTypeOther",
        x="0",
        y="501",
        width="440",
        height="620",
    )
    title_row = ET.SubElement(
        card,
        "XCUIElementTypeOther",
        type="XCUIElementTypeOther",
        x="20",
        y="522",
        width="400",
        height="28",
    )
    ET.SubElement(
        title_row,
        "XCUIElementTypeStaticText",
        type="XCUIElementTypeStaticText",
        name=place,
        label=place,
        enabled="true",
    )
    ET.SubElement(
        card,
        "XCUIElementTypeOther",
        type="XCUIElementTypeOther",
        name="Historical landmark, Wheelchair accessible",
        enabled="true",
    )
    directions_row = ET.SubElement(
        card,
        "XCUIElementTypeCell",
        type="XCUIElementTypeCell",
        name="Directions",
        x="20",
        y="621",
        width="127",
        height="48",
    )
    ET.SubElement(
        directions_row,
        "XCUIElementTypeButton",
        type="XCUIElementTypeButton",
        name="Directions",
        label="Directions",
        enabled="true",
        x="20",
        y="621",
        width="127",
        height="48",
    )
    return root


def test_google_maps_native_place_page_is_verified(demo):
    assert demo.maps_page_matches("com.google.Maps", google_maps_place()) is True


def test_google_maps_native_page_rejects_wrong_query(demo):
    assert demo.maps_page_matches(
        "com.google.Maps",
        google_maps_place(query="Another Place"),
    ) is False


def test_google_maps_native_signals_must_share_place_card(demo):
    root = google_maps_place()
    card = next(n for n in root if n.get("y") == "501")
    landmark = next(n for n in card if n.get("name", "").startswith("Historical landmark"))
    card.remove(landmark)
    unrelated = ET.SubElement(
        root,
        "XCUIElementTypeOther",
        type="XCUIElementTypeOther",
        x="0",
        y="300",
        width="440",
        height="100",
    )
    unrelated.append(landmark)

    assert demo.maps_page_matches("com.google.Maps", root) is False


def test_google_maps_native_rejects_signals_split_across_sibling_cells(demo):
    root = ET.Element("Application", width="440", height="956")
    ET.SubElement(
        root,
        "XCUIElementTypeTextField",
        type="XCUIElementTypeTextField",
        name="SearchHeaderSearchTxtView",
        value="Ferry Building San Francisco",
        enabled="true",
    )
    page = ET.SubElement(
        root,
        "XCUIElementTypeOther",
        type="XCUIElementTypeOther",
        x="0",
        y="50",
        width="440",
        height="900",
    )
    title_cell = ET.SubElement(page, "XCUIElementTypeCell", type="XCUIElementTypeCell")
    ET.SubElement(
        title_cell,
        "XCUIElementTypeStaticText",
        type="XCUIElementTypeStaticText",
        name="Ferry Building",
        label="Ferry Building",
        enabled="true",
    )
    action_cell = ET.SubElement(page, "XCUIElementTypeCell", type="XCUIElementTypeCell")
    ET.SubElement(
        action_cell,
        "XCUIElementTypeOther",
        type="XCUIElementTypeOther",
        name="Historical landmark, Wheelchair accessible",
        enabled="true",
    )
    ET.SubElement(
        action_cell,
        "XCUIElementTypeButton",
        type="XCUIElementTypeButton",
        name="Directions",
        label="Directions",
        enabled="true",
        x="20",
        y="621",
        width="127",
        height="48",
    )

    assert demo.maps_page_matches("com.google.Maps", root) is False


def test_google_maps_native_rejects_a_page_sized_generic_wrapper(demo):
    root = google_maps_place()
    card = next(n for n in root if n.get("y") == "501")
    card.set("y", "47")
    card.set("height", "909")

    assert demo.maps_page_matches("com.google.Maps", root) is False


def test_google_maps_native_query_must_be_outside_the_place_sheet(demo):
    root = google_maps_place()
    query = next(n for n in root if n.get("name") == "SearchHeaderSearchTxtView")
    card = next(n for n in root if n.get("y") == "501")
    root.remove(query)
    card.insert(0, query)

    assert demo.maps_page_matches("com.google.Maps", root) is False


def test_google_maps_native_directions_must_be_inside_the_place_sheet(demo):
    root = google_maps_place()
    directions = next(
        n for n in root.iter()
        if n.get("type", "").endswith("Button") and n.get("name") == "Directions"
    )
    directions.set("y", "450")

    assert demo.maps_page_matches("com.google.Maps", root) is False


@pytest.mark.parametrize("value", ("not-a-number", "nan", "inf"))
def test_google_maps_native_rejects_invalid_geometry(demo, value):
    root = google_maps_place()
    directions = next(
        n for n in root.iter()
        if n.get("type", "").endswith("Button") and n.get("name") == "Directions"
    )
    directions.set("x", value)

    assert demo.maps_page_matches("com.google.Maps", root) is False


def test_google_maps_query_tracks_event_fixture(demo, monkeypatch):
    monkeypatch.setitem(demo.EVENT, "venue", "Pier 39")
    monkeypatch.setitem(demo.EVENT, "venue_query", "Pier 39, San Francisco")

    assert demo.maps_page_matches(
        "com.google.Maps",
        google_maps_place(query="Pier 39 San Francisco", place="Pier 39"),
    ) is True
