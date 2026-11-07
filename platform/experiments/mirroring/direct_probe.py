"""Isolated direct-device experiment. No identifiers or raw device errors on stdout.

Uses a separately reviewed, source-built CLI; does not install it or any phone app.
Only an already-connected physical iOS device is eligible. Mutations are never retried.
"""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import struct
import tempfile
import time


def emit(**record):
    print(json.dumps(record), flush=True)


def target():
    with tempfile.TemporaryDirectory(prefix="phoneuse-device-discovery-") as folder:
        output = Path(folder) / "devices.json"
        subprocess.run(["xcrun", "devicectl", "list", "devices", "--json-output", str(output)],
                       capture_output=True, check=True, timeout=20)
        devices = json.loads(output.read_text()).get("result", {}).get("devices", [])
    connected = [d for d in devices
                 if d.get("connectionProperties", {}).get("tunnelState") == "connected"
                 and d.get("hardwareProperties", {}).get("platform") == "iOS"
                 and d.get("hardwareProperties", {}).get("reality") == "physical"]
    if len(connected) != 1:
        raise RuntimeError("Exactly one connected physical iOS device is required")
    item = connected[0]
    emit(type="target", count=1,
         transport=item.get("connectionProperties", {}).get("transportType"),
         os_version=item.get("deviceProperties", {}).get("osVersionNumber"))
    return item["hardwareProperties"]["udid"]


def structure(obj):
    """Preserve diagnostic shape and numeric capabilities, omit string payloads/IDs."""
    if isinstance(obj, dict):
        return {k: structure(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [structure(v) for v in obj]
    return "<string>" if isinstance(obj, str) else obj


def observe(binary):
    if not binary:
        return None
    try:
        result = subprocess.run([binary, "status"], capture_output=True, text=True, timeout=8)
        return json.loads(result.stdout.splitlines()[0]).get("desktop")
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return {"measurement_unavailable": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["screenshot", "mirror-screenshot", "display-info", "surfaces", "ui", "touch", "text", "swipe", "home", "key"])
    parser.add_argument("--binary", default="/tmp/phoneuse-direct-build/release/iphone-use")
    parser.add_argument("--observer", help="Path to the built native mirror-probe for focus/cursor endpoints")
    parser.add_argument("--raw-hid", help="Minimal HID helper that bypasses unsupported display-info queries")
    parser.add_argument("--indigo-target", type=int, choices=range(11), help="Experimental display-targeted Indigo digitizer variant")
    parser.add_argument("--touch-layout", choices=["original", "minimal"], default="original")
    parser.add_argument("--wireless-surface", action="store_true", help="Derive touchscreen surface from the active wireless display")
    parser.add_argument("--register-wireless-surface", action="store_true", help="Create, use and remove a temporary wireless touchscreen on ONE connection")
    parser.add_argument("--display-selector", choices=["numeric", "unique"], default="numeric")
    parser.add_argument("--observed-mirror-field", action="store_true", help="Controlled probe into an observed live mirrored session; coordinates exclude Mac chrome")
    parser.add_argument("--output", help="Screenshot destination; must be within temporary storage")
    parser.add_argument("--image", help="Recently observed 650-wide PNG for coordinate conversion")
    parser.add_argument("--x", type=float)
    parser.add_argument("--y", type=float)
    parser.add_argument("--x2", type=float)
    parser.add_argument("--y2", type=float)
    parser.add_argument("--key", choices=["tab", "space", "escape", "up", "down", "left", "right", "delete", "page-down", "page-up"])
    parser.add_argument("--text", default="phoneuse-probe", help="Printable US ASCII only; no submission/newline or clipboard")
    parser.add_argument("--shift", action="store_true")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--observed-unlocked", action="store_true")
    args = parser.parse_args()
    if args.operation == "text" and (len(args.text) > 256 or any(not 32 <= ord(c) <= 126 for c in args.text)):
        parser.error("Text must be at most 256 printable ASCII characters; nothing sent")
    mutation = args.operation in {"touch", "text", "swipe", "home", "key"}
    if mutation and not args.send:
        parser.error("Phone input requires --send after observing the current phone screen")
    if mutation and not args.observed_unlocked and not (args.raw_hid and args.observed_mirror_field):
        parser.error("Confirm the current phone screen is unlocked with --observed-unlocked")
    udid = target()
    command = [args.binary, "--no-daemon", args.operation, "--udid", udid]
    if args.operation in {"screenshot", "mirror-screenshot"}:
        if not args.output:
            parser.error("screenshot requires --output in temporary storage")
        output = Path(args.output).resolve()
        roots = [Path("/tmp").resolve(), Path(tempfile.gettempdir()).resolve()]
        if not any(output.is_relative_to(root) for root in roots):
            parser.error("Screenshots must stay outside the repository in temporary storage")
        if args.operation == "screenshot":
            command += ["--max-width", "650", "--output", str(output)]
        else:
            query = subprocess.run([args.binary,"--no-daemon","invoke","--udid",udid,
                "com.apple.coredevice.deviceinfo","com.apple.coredevice.feature.getdisplayinfo",
                "--action","com.apple.coredevice.action.displayinfo"], capture_output=True, text=True, timeout=25, check=True)
            displays = json.loads(query.stdout).get("displays", [])
            candidates = [d for d in displays if "wireless" in d.get("type", {})
                          and d.get("nativeSize", [0,0])[0] > 0 and d.get("uniqueId")]
            if len(candidates) != 1:
                raise RuntimeError("Need exactly one active wireless display")
            command = [args.binary,"--no-daemon","invoke","--udid",udid,
                "com.apple.coredevice.screencaptureservice","com.apple.coredevice.feature.capturescreenshot",
                "--input",json.dumps({"requestedFormat":"png","displayUniqueID":candidates[0]["uniqueId"]}),
                "--dump-data",str(output)]
    elif args.operation == "display-info":
        command = [args.binary, "--no-daemon", "invoke", "--udid", udid,
                   "com.apple.coredevice.deviceinfo", "com.apple.coredevice.feature.getdisplayinfo",
                   "--action", "com.apple.coredevice.action.displayinfo"]
    elif args.operation == "surfaces":
        # Avoid the upstream command's unrelated getdisplayinfo query (times out on this iOS).
        command = [args.binary, "--no-daemon", "invoke", "--udid", udid,
                   "com.apple.coredevice.hid.universalhidservice", "--no-envelope", "--input",
                   json.dumps({"featureIdentifier": "com.apple.coredevice.feature.remote.universalhidservice",
                               "messageType": "Request", "payload": {"connectedServices": {}}})]
    elif args.operation == "ui":
        command += ["--find", "Search"]
    elif args.operation in {"touch", "swipe"} and not args.raw_hid:
        coordinates = [args.x, args.y] + ([args.x2, args.y2] if args.operation == "swipe" else [])
        if any(v is None or not 0 <= v <= 1 for v in coordinates):
            parser.error("Coordinates must be normalized to the current PHONE image (0..1)")
        if not args.image:
            parser.error("Coordinate input requires a recently observed PNG via --image")
        image = Path(args.image)
        if not 0 <= time.time() - image.stat().st_mtime <= 90:
            parser.error("Observation is stale; take and inspect a fresh screenshot")
        with image.open("rb") as handle:
            header = handle.read(24)
        if header[:8] != b"\x89PNG\r\n\x1a\n" or len(header) != 24:
            parser.error("Observation must be a PNG")
        width, height = struct.unpack(">II", header[16:24])
        if width != 650 or height > 5000:
            parser.error("Use the wrapper's 650-wide screenshot")
        pixels = [v * (width if index % 2 == 0 else height) for index, v in enumerate(coordinates)]
        command += [str(v) for v in pixels] + ["--image-width", str(width)]
    elif args.operation == "text":
        command += [args.text]
    elif args.operation == "home":
        command = [args.binary, "--no-daemon", "button", "home", "--udid", udid]
    stdin_payload = None
    if args.raw_hid:
        if args.operation not in {"text", "touch", "swipe", "home", "key"}:
            parser.error("Raw helper supports text, touch, swipe and home only")
        command = [args.raw_hid, "--send"]
        payload = {"udid": udid, "operation": "tap" if args.operation == "touch" else args.operation,
                   "field_ready": True, "text": args.text}
        payload["touch_layout"] = args.touch_layout
        if args.operation == "key":
            if not args.key:
                parser.error("key requires --key")
            payload.update(key=args.key, shift=args.shift)
        if args.operation in {"touch", "swipe"}:
            coordinates = [args.x,args.y] + ([args.x2,args.y2] if args.operation == "swipe" else [])
            if any(v is None or not 0 <= v <= 1 for v in coordinates):
                parser.error("Raw HID coordinates must be normalized PHONE coordinates")
            payload.update(dict(zip(["x","y","x2","y2"], coordinates)))
            if args.indigo_target is not None:
                payload["digitizer_target"] = args.indigo_target
            if args.wireless_surface or args.register_wireless_surface:
                query = subprocess.run([args.binary,"--no-daemon","invoke","--udid",udid,
                    "com.apple.coredevice.deviceinfo","com.apple.coredevice.feature.getdisplayinfo",
                    "--action","com.apple.coredevice.action.displayinfo"], capture_output=True, text=True, timeout=25, check=True)
                candidates = [d for d in json.loads(query.stdout).get("displays", [])
                              if "wireless" in d.get("type", {}) and d.get("nativeSize", [0,0])[0] > 0]
                if len(candidates) != 1 or not isinstance(candidates[0].get("displayId"), int):
                    raise RuntimeError("Need exactly one active wireless display")
                payload["touch_surface"] = 0x100 + candidates[0]["displayId"]
                if args.register_wireless_surface:
                    inventory = subprocess.run([args.binary,"--no-daemon","invoke","--udid",udid,
                        "com.apple.coredevice.hid.universalhidservice","--no-envelope","--input",
                        json.dumps({"featureIdentifier":"com.apple.coredevice.feature.remote.universalhidservice",
                                    "messageType":"Request","payload":{"connectedServices":{}}})],
                        capture_output=True,text=True,timeout=20,check=True)
                    services = json.loads(inventory.stdout).get("connectedServices")
                    if not isinstance(services,list) or any(s.get("_ServiceID") == payload["touch_surface"] for s in services):
                        raise RuntimeError("Refusing to replace an existing HID service")
                    # This diagnostic request can restart/throttle this device's HID daemon.
                    time.sleep(11)
                    payload["register_display"] = str(candidates[0]["displayId"]) if args.display_selector == "numeric" else candidates[0]["uniqueId"]
                emit(type="touch_route", display_kind="wireless", surface_protocol_id=payload["touch_surface"])
        stdin_payload = json.dumps(payload)
    before = observe(args.observer)
    started = time.monotonic()
    result = subprocess.run(command, input=stdin_payload, capture_output=True, text=True, timeout=40,
                            env={**os.environ, "IPHONE_USE_NO_DAEMON": "1"})
    after = observe(args.observer)
    if args.raw_hid:
        for line in result.stdout.splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") in {"temporary_surface", "temporary_surface_cleanup", "direct_hid"}:
                emit(**{key: value for key, value in record.items() if key in {
                    "type", "created", "error_reply", "transport_flushed", "phone_effect", "mechanism", "error"}})
    emit(type="result", operation=args.operation, exit_code=result.returncode,
         elapsed_ms=round((time.monotonic() - started) * 1000, 1), before=before, after=after,
         outcome="dispatched_unverified" if mutation and not result.returncode else "completed" if not result.returncode else "failed")
    if result.returncode:
        error = result.stderr.lower()
        emit(type="error_category", category="locked" if "locked" in error else "connection" if "connection" in error or "tunnel" in error else "other")
        # Only surface known protocol diagnostics, never device names/IDs or serialized blobs.
        match = re.search(r'Action [^\n"]{0,150}is not implemented', result.stderr)
        if match:
            emit(type="protocol_error", detail=match.group(0))
        return result.returncode
    if args.operation in {"display-info", "surfaces"}:
        emit(type="diagnostic_structure", data=structure(json.loads(result.stdout)))
    elif args.operation == "ui":
        emit(type="ui_read", matching_lines=len(result.stdout.splitlines()))
    elif args.operation in {"screenshot", "mirror-screenshot"}:
        output.chmod(0o600)
        emit(type="private_screenshot", path=str(output), bytes=output.stat().st_size)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        emit(type="failure", category=type(exc).__name__)
        raise SystemExit(1)
