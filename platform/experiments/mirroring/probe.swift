import AppKit
import ApplicationServices
import ScreenCaptureKit
import CryptoKit
import ImageIO
import Vision
import Darwin

// Diagnostic only. Activation and temporary image export require explicit setup/preview commands.
let mirrorBundle = "com.apple.ScreenContinuity"
func emit(_ value: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
}
func failure(_ message: String) -> Never { emit(["error": message]); exit(1) }
func desktop() -> [String: Any] {
    let p = CGEvent(source: nil)?.location ?? .zero
    var focused: CFTypeRef?
    let focusedError = AXUIElementCopyAttributeValue(AXUIElementCreateSystemWide(), kAXFocusedApplicationAttribute as CFString, &focused)
    var focusedPid: pid_t = -1
    if focusedError == .success, let focused {
        AXUIElementGetPid(focused as! AXUIElement, &focusedPid)
    }
    // Some sessions do not expose the system-wide focused-app attribute.
    // Ask running applications for AXFrontmost instead of trusting cached NSWorkspace focus.
    if focusedPid == -1 && AXIsProcessTrusted() {
        for app in NSWorkspace.shared.runningApplications where app.activationPolicy == .regular {
            if value(AXUIElementCreateApplication(app.processIdentifier), kAXFrontmostAttribute) as? Bool == true {
                focusedPid = app.processIdentifier; break
            }
        }
    }
    let frontWindow = (CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]])?
        .first { ($0[kCGWindowLayer as String] as? Int) == 0 }
    return ["foreground_pid": focusedPid, "focus_measurement_valid": focusedPid != -1,
            "workspace_pid": NSWorkspace.shared.frontmostApplication?.processIdentifier ?? -1,
            "front_window_pid": frontWindow?[kCGWindowOwnerPID as String] as? Int ?? -1,
            "cursor": [p.x, p.y]]
}
func value(_ element: AXUIElement, _ attribute: String) -> CFTypeRef? {
    var result: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &result) == .success else { return nil }
    return result
}
@main struct Probe {
    static func main() async {
        setbuf(stdout, nil)
        DispatchQueue.global().asyncAfter(deadline: .now() + 25) { failure("Probe exceeded 25-second deadline") }
        let args = Array(CommandLine.arguments.dropFirst())
        let command = args.first ?? "status"
        if command == "request-permissions" {
            let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
            let accessibility = AXIsProcessTrustedWithOptions(options)
            let capture = CGRequestScreenCaptureAccess()
            emit(["type": "permission_request", "accessibility": accessibility, "screen_capture": capture,
                  "next": "Grant permissions in System Settings, then rerun status; a restart may be required"])
            return
        }
        let apps = NSRunningApplication.runningApplications(withBundleIdentifier: mirrorBundle)
        let permission = CGPreflightScreenCaptureAccess()
        emit(["type": "status", "screen_capture": permission,
              "accessibility": AXIsProcessTrusted(), "mirroring_running": !apps.isEmpty,
              "mirroring_pid": apps.first?.processIdentifier ?? -1,
              "desktop": desktop(), "os": ProcessInfo.processInfo.operatingSystemVersionString])
        if command == "status" { return }
        guard ["show", "minimize", "show-host", "occlude", "restore-position", "inspect", "windows", "capture", "tap", "drag", "scroll", "text", "spotlight", "home"].contains(command) else { failure("Unknown command") }
        guard let app = apps.first else { failure("Open and connect iPhone Mirroring manually first") }
        if command == "minimize" {
            guard let window = (value(AXUIElementCreateApplication(app.processIdentifier), kAXWindowsAttribute) as? [AXUIElement])?.first,
                  AXUIElementSetAttributeValue(window, kAXMinimizedAttribute as CFString, kCFBooleanTrue) == .success else { failure("Cannot minimize main window") }
            emit(["type": "setup_minimize", "minimized": value(window, kAXMinimizedAttribute) as? Bool ?? false]); return
        }
        if command == "show" {
            for axWindow in value(AXUIElementCreateApplication(app.processIdentifier), kAXWindowsAttribute) as? [AXUIElement] ?? [] {
                AXUIElementSetAttributeValue(axWindow, kAXMinimizedAttribute as CFString, kCFBooleanFalse)
                AXUIElementPerformAction(axWindow, kAXRaiseAction as CFString)
            }
            emit(["type": "setup_show", "activated": app.activate(options: [.activateAllWindows])])
            return
        }
        if command == "show-host" {
            guard let host = NSRunningApplication.runningApplications(withBundleIdentifier: "com.openai.codex").first else { failure("ChatGPT host not running") }
            emit(["type": "setup_show_host", "activated": host.activate(options: [.activateAllWindows])])
            return
        }
        if command == "inspect" {
            guard AXIsProcessTrusted() else { failure("Accessibility permission required") }
            let root = AXUIElementCreateApplication(app.processIdentifier)
            var nodes = 0
            func walk(_ element: AXUIElement, _ depth: Int) {
                guard depth < 8, nodes < 200 else { return }; nodes += 1
                var actions: CFArray?
                AXUIElementCopyActionNames(element, &actions)
                // Deliberately omit titles, values, labels and other personal text.
                emit(["type": "ax_node", "depth": depth,
                      "role": value(element, kAXRoleAttribute) as? String ?? "unknown",
                      "minimized": (value(element, kAXMinimizedAttribute) as? Bool).map { $0 as Any } ?? NSNull(),
                      "actions": actions as? [String] ?? []])
                for child in value(element, kAXChildrenAttribute) as? [AXUIElement] ?? [] { walk(child, depth + 1) }
            }
            for window in value(root, kAXWindowsAttribute) as? [AXUIElement] ?? [] { walk(window, 0) }
            return
        }
        // Actual ScreenCaptureKit access is authoritative; preflight can lag a settings change.
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: false)
            let windows = content.windows.filter { $0.owningApplication?.processID == app.processIdentifier && $0.windowLayer == 0 && $0.frame.width > 100 && $0.frame.height > 100 }
            for candidate in content.windows where candidate.owningApplication?.processID == app.processIdentifier {
                emit(["type": "window", "id": candidate.windowID, "layer": candidate.windowLayer,
                      "on_screen": candidate.isOnScreen, "bounds": [candidate.frame.minX, candidate.frame.minY, candidate.frame.width, candidate.frame.height]])
            }
            if command == "windows" { return }
            var selected = windows
            if let flag = args.firstIndex(of: "--window"), args.count > flag + 1, let id = UInt32(args[flag + 1]) {
                selected = content.windows.filter { $0.owningApplication?.processID == app.processIdentifier && $0.windowID == id }
            }
            guard selected.count == 1, let window = selected.first else { failure("Select a Mirroring window explicitly with --window ID") }
            if let front = (CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]])?.first(where: { ($0[kCGWindowLayer as String] as? Int) == 0 }),
               let bounds = front[kCGWindowBounds as String] as? NSDictionary,
               let rect = CGRect(dictionaryRepresentation: bounds) {
                emit(["type": "occlusion", "fully_inside_front_window": rect.contains(window.frame),
                      "front_window_is_target": front[kCGWindowNumber as String] as? UInt32 == window.windowID])
                if command == "occlude" || command == "restore-position" {
                    guard front[kCGWindowOwnerPID as String] as? Int32 != app.processIdentifier,
                          let axWindow = (value(AXUIElementCreateApplication(app.processIdentifier), kAXWindowsAttribute) as? [AXUIElement])?.first else { failure("Need another application in front and a main AX window") }
                    let save = FileManager.default.temporaryDirectory.appendingPathComponent("phoneuse-mirror-position.json")
                    var point: CGPoint
                    if command == "occlude" {
                        guard rect.width >= window.frame.width + 20, rect.height >= window.frame.height + 20 else { failure("Foreground window is too small to cover phone") }
                        try JSONSerialization.data(withJSONObject: ["x": window.frame.minX, "y": window.frame.minY]).write(to: save, options: .atomic)
                        point = CGPoint(x: rect.minX + 10, y: rect.minY + 10)
                    } else {
                        guard let saved = try JSONSerialization.jsonObject(with: Data(contentsOf: save)) as? [String: Double], let x = saved["x"], let y = saved["y"] else { failure("No saved position") }
                        point = CGPoint(x: x, y: y)
                    }
                    guard let axPoint = AXValueCreate(.cgPoint, &point), AXUIElementSetAttributeValue(axWindow, kAXPositionAttribute as CFString, axPoint) == .success else { failure("Window move rejected") }
                    emit(["type": "setup_window_move", "command": command, "desktop": desktop()]); return
                }
            }
            let filter = SCContentFilter(desktopIndependentWindow: window)
            let config = SCStreamConfiguration()
            config.width = Int(window.frame.width * 2); config.height = Int(window.frame.height * 2)
            config.showsCursor = false
            if command == "capture" {
                let before = desktop()
                for index in 0..<5 {
                    let start = ProcessInfo.processInfo.systemUptime
                    let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
                    let captureMS = (ProcessInfo.processInfo.systemUptime - start) * 1000
                    if index == 0 && args.contains("--preview") {
                        let url = FileManager.default.temporaryDirectory.appendingPathComponent("phoneuse-mirror-preview.png")
                        guard let dest = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil) else { failure("Cannot export temporary preview") }
                        CGImageDestinationAddImage(dest, image, nil)
                        guard CGImageDestinationFinalize(dest) else { failure("Cannot finalize temporary preview") }
                        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
                        emit(["type": "temporary_preview", "path": url.path])
                    }
                    if index == 0 && args.contains("--check-text") {
                        let request = VNRecognizeTextRequest()
                        try VNImageRequestHandler(cgImage: image).perform([request])
                        let texts = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string.lowercased() }
                        emit(["type": "ocr_check", "probe_text_present": texts.contains { $0.contains("phoneuse-probe") }, "calculator_present": texts.contains { $0.contains("calculator") }])
                    }
                    let bytes = image.dataProvider?.data as Data? ?? Data()
                    emit(["type": "frame", "sample": index, "width": image.width, "height": image.height,
                          "sha256": SHA256.hash(data: bytes).description,
                          "capture_ms": captureMS])
                    try await Task.sleep(for: .milliseconds(400))
                }
                emit(["type": "capture_complete", "before": before, "after": desktop()]); return
            }
            guard AXIsProcessTrusted() else { failure("Accessibility permission required for input") }
            guard args.contains("--send") else { failure("Input probes require explicit --send") }
            let before = desktop()
            guard before["focus_measurement_valid"] as? Bool == true else { failure("Cannot measure live focus; refusing input") }
            guard args.contains("--allow-front") || before["foreground_pid"] as? Int32 != app.processIdentifier else { failure("Focus another application first to test background input") }
            let source = CGEventSource(stateID: .privateState)
            guard let source else { failure("Cannot create private event source") }
            if ["tap", "scroll"].contains(command), args.count >= 3,
               let x = Double(args[1]), let y = Double(args[2]),
               [x,y].allSatisfy({ $0.isFinite && (0...1).contains($0) }), args.contains("--hover") {
                let point = CGPoint(x: window.frame.minX + x * window.frame.width, y: window.frame.minY + y * window.frame.height)
                let localPoint = NSPoint(x: x * window.frame.width, y: (1-y) * window.frame.height)
                let localLocation = NSEvent.mouseEvent(with: .mouseMoved, location: localPoint, modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: Int(window.windowID), context: nil,
                    eventNumber: 1, clickCount: 0, pressure: 0)?.cgEvent?.location
                guard let event = CGEvent(mouseEventSource: source, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left) else { failure("Cannot create local hover") }
                if args.contains("--local-event"), let localLocation { event.location = localLocation }
                event.flags = []
                for field in [51, 91, 92] { event.setIntegerValueField(CGEventField(rawValue: UInt32(field))!, value: Int64(window.windowID)) }
                event.postToPid(app.processIdentifier)
                try await Task.sleep(for: .milliseconds(100))
            }
            if args.contains("--make-key") || args.contains("--key-record-only") || args.contains("--record-tap") {
                // Experimental layout documented by phone-harness background.py / yabai.
                guard let sky = dlopen("/System/Library/PrivateFrameworks/SkyLight.framework/SkyLight", RTLD_NOW),
                      let services = dlopen("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices", RTLD_NOW),
                      let getSymbol = dlsym(services, "GetProcessForPID"),
                      let frontSymbol = dlsym(sky, "_SLPSSetFrontProcessWithOptions"),
                      let postSymbol = dlsym(sky, "SLPSPostEventRecordTo") else { failure("Private API symbols unavailable") }
                typealias GetPSN = @convention(c) (Int32, UnsafeMutableRawPointer) -> Int32
                typealias SetFront = @convention(c) (UnsafeMutableRawPointer, UInt32, UInt32) -> Int32
                typealias PostRecord = @convention(c) (UnsafeMutableRawPointer, UnsafeMutableRawPointer) -> Int32
                let getPSN = unsafeBitCast(getSymbol, to: GetPSN.self)
                let setFront = unsafeBitCast(frontSymbol, to: SetFront.self)
                let post = unsafeBitCast(postSymbol, to: PostRecord.self)
                let psn = UnsafeMutableRawPointer.allocate(byteCount: 8, alignment: 4)
                defer { psn.deallocate() }
                psn.initializeMemory(as: UInt8.self, repeating: 0, count: 8)
                guard getPSN(app.processIdentifier, psn) == 0 else { failure("Cannot resolve process serial number") }
                let record = UnsafeMutableRawPointer.allocate(byteCount: 0xf8, alignment: 8)
                defer { record.deallocate() }
                record.initializeMemory(as: UInt8.self, repeating: 0, count: 0xf8)
                record.storeBytes(of: UInt8(0xf8), toByteOffset: 4, as: UInt8.self)
                record.storeBytes(of: UInt8(0x10), toByteOffset: 0x3a, as: UInt8.self)
                record.storeBytes(of: window.windowID, toByteOffset: 0x3c, as: UInt32.self)
                if args.contains("--record-tap") {
                    guard command == "tap", args.count >= 3, let x = Double(args[1]), let y = Double(args[2]),
                          x.isFinite, y.isFinite, (0...1).contains(x), (0...1).contains(y) else { failure("Private record tap needs normalized tap coordinates") }
                    record.storeBytes(of: window.frame.minX + x * window.frame.width, toByteOffset: 0x10, as: Double.self)
                    record.storeBytes(of: window.frame.minY + y * window.frame.height, toByteOffset: 0x18, as: Double.self)
                    record.storeBytes(of: x * window.frame.width, toByteOffset: 0x20, as: Double.self)
                    record.storeBytes(of: y * window.frame.height, toByteOffset: 0x28, as: Double.self)
                } else {
                    record.advanced(by: 0x20).initializeMemory(as: UInt8.self, repeating: 0xff, count: 16)
                }
                let callsSetFront = !args.contains("--record-tap") && !args.contains("--key-record-only")
                let frontResult = callsSetFront ? setFront(psn, window.windowID, 0x200) : Int32(-999)
                var results: [Int32] = []
                for type: UInt8 in [1, 2] {
                    record.storeBytes(of: type, toByteOffset: 8, as: UInt8.self)
                    results.append(post(psn, record))
                    try await Task.sleep(for: .milliseconds(40))
                }
                emit(["type": "private_record", "set_front_called": callsSetFront, "set_front_result": frontResult, "post_results": results, "desktop": desktop()])
                if args.contains("--record-tap") {
                    try await Task.sleep(for: .milliseconds(300))
                    emit(["type": "input_dispatched", "before": before, "after": desktop(), "phone_effect": "unverified", "mechanism": "SkyLight record without SetFront"])
                    return
                }
            }
            if command == "scroll" {
                guard args.count >= 3, let x = Double(args[1]), let y = Double(args[2]),
                      [x,y].allSatisfy({ $0.isFinite && (0...1).contains($0) }) else { failure("scroll needs normalized full-window x y") }
                let point = CGPoint(x: window.frame.minX + x * window.frame.width, y: window.frame.minY + y * window.frame.height)
                let localLocation = NSEvent.mouseEvent(with: .mouseMoved,
                    location: NSPoint(x: x * window.frame.width, y: (1-y) * window.frame.height), modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: Int(window.windowID), context: nil,
                    eventNumber: 1, clickCount: 0, pressure: 0)?.cgEvent?.location
                if args.contains("--primed-scroll") {
                    guard let moved = NSEvent.mouseEvent(with: .mouseMoved, location: .zero, modifierFlags: [],
                        timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: Int(window.windowID), context: nil,
                        eventNumber: 1, clickCount: 0, pressure: 0)?.cgEvent,
                        let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "CGEventSetWindowLocation") else { failure("Cannot construct scroll primer") }
                    typealias SetWindowLocation = @convention(c) (CGEvent, CGPoint) -> Void
                    moved.location = point
                    unsafeBitCast(symbol, to: SetWindowLocation.self)(moved, CGPoint(x:x*window.frame.width,y:y*window.frame.height))
                    moved.flags = .maskCommand
                    for field in [51,91,92] { moved.setIntegerValueField(CGEventField(rawValue:UInt32(field))!,value:Int64(window.windowID)) }
                    moved.setIntegerValueField(.mouseEventSubtype,value:3)
                    moved.postToPid(app.processIdentifier)
                    try await Task.sleep(for:.milliseconds(100))
                }
                for step in 0...13 {
                    if args.contains("--unphased"), step == 0 || step == 13 { continue }
                    let phase: Int64 = step == 0 ? 1 : step == 13 ? 4 : 2
                    guard let event = CGEvent(scrollWheelEvent2Source: args.contains("--primed-scroll") ? CGEventSource(stateID:.hidSystemState) : source, units: .pixel, wheelCount: 2,
                                              wheel1: step == 0 || step == 13 ? 0 : (args.contains("--positive") ? 40 : -40), wheel2: 0, wheel3: 0) else { failure("Cannot create scroll event") }
                    event.location = args.contains("--local-event") ? (localLocation ?? point) : point; event.flags = []
                    event.setIntegerValueField(CGEventField(rawValue: 51)!, value: Int64(window.windowID))
                    event.setIntegerValueField(.eventTargetUnixProcessID, value: Int64(app.processIdentifier))
                    event.setIntegerValueField(.scrollWheelEventScrollPhase, value: phase)
                    event.setIntegerValueField(.scrollWheelEventIsContinuous, value: 1)
                    if args.contains("--unphased") {
                        event.setIntegerValueField(.scrollWheelEventScrollPhase, value: 0)
                        event.setIntegerValueField(.scrollWheelEventIsContinuous, value: 0)
                    }
                    event.setIntegerValueField(.mouseEventWindowUnderMousePointer, value: Int64(window.windowID))
                    event.setIntegerValueField(.mouseEventWindowUnderMousePointerThatCanHandleThisEvent, value: Int64(window.windowID))
                    if args.contains("--background-shape") {
                        guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "CGEventSetWindowLocation") else { failure("Window-location SPI unavailable") }
                        typealias SetWindowLocation = @convention(c) (CGEvent, CGPoint) -> Void
                        event.location = args.contains("--local-event") ? (localLocation ?? point) : point
                        unsafeBitCast(symbol, to: SetWindowLocation.self)(event, CGPoint(x: x * window.frame.width, y: y * window.frame.height))
                        event.setIntegerValueField(.mouseEventSubtype, value: 3)
                        event.flags = before["foreground_pid"] as? Int32 == app.processIdentifier ? [] : .maskCommand
                    }
                    if args.contains("--no-command") { event.flags = [] }
                    if step == 2, let native = NSEvent(cgEvent: event) {
                        emit(["type": "scroll_shape", "window_matches": native.windowNumber == Int(window.windowID),
                              "location_in_window": [native.locationInWindow.x,native.locationInWindow.y],
                              "delta_y": native.scrollingDeltaY, "precise": native.hasPreciseScrollingDeltas,
                              "phase": native.phase.rawValue])
                    }
                    event.postToPid(app.processIdentifier)
                    try await Task.sleep(for: .milliseconds(20))
                }
            } else if command == "tap" || command == "drag" {
                guard args.count >= 3, let x = Double(args[1]), let y = Double(args[2]), x.isFinite, y.isFinite,
                      x >= 0, x <= 1, y >= 0, y <= 1 else { failure("tap needs normalized full-window x y") }
                // Full-window coordinates for the probe. Production needs a calibrated phone viewport.
                var x2 = x, y2 = y
                if command == "drag" {
                    guard args.count >= 5, let endX = Double(args[3]), let endY = Double(args[4]),
                          [endX,endY].allSatisfy({ $0.isFinite && (0...1).contains($0) }) else { failure("drag needs start x y and end x y") }
                    x2 = endX; y2 = endY
                }
                let types: [CGEventType] = command == "drag" ? [.leftMouseDown] + Array(repeating: .leftMouseDragged, count: 30) + [.leftMouseUp] : [.leftMouseDown, .leftMouseUp]
                for (index,type) in types.enumerated() {
                    let t = command == "drag" ? min(1,Double(index)/30) : 0
                    let px = x+(x2-x)*t, py = y+(y2-y)*t
                    let point = CGPoint(x: window.frame.minX + px * window.frame.width, y: window.frame.minY + py * window.frame.height)
                    let nsType: NSEvent.EventType = type == .leftMouseDown ? .leftMouseDown : type == .leftMouseUp ? .leftMouseUp : .leftMouseDragged
                    let native = NSEvent.mouseEvent(with: nsType,
                        location: NSPoint(x: px * window.frame.width, y: (1-py) * window.frame.height),
                        modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                        windowNumber: Int(window.windowID), context: nil, eventNumber: 1, clickCount: 1,
                        pressure: type == .leftMouseUp ? 0 : 1)
                    guard let event = args.contains("--local-event") || args.contains("--background-shape") ? native?.cgEvent : CGEvent(mouseEventSource: source, mouseType: type, mouseCursorPosition: point, mouseButton: .left) else { failure("Cannot create mouse event") }
                    event.flags = []
                    if args.contains("--background-shape") {
                        guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "CGEventSetWindowLocation") else { failure("Window-location SPI unavailable") }
                        typealias SetWindowLocation = @convention(c) (CGEvent, CGPoint) -> Void
                        let setLocation = unsafeBitCast(symbol, to: SetWindowLocation.self)
                        event.location = point
                        setLocation(event, CGPoint(x: px * window.frame.width, y: py * window.frame.height))
                        event.setIntegerValueField(.mouseEventSubtype, value: 3)
                        event.setIntegerValueField(.mouseEventButtonNumber, value: 0)
                        event.flags = before["foreground_pid"] as? Int32 == app.processIdentifier ? [] : .maskCommand
                    }
                    // Field 51 maps to NSEvent.windowNumber in the local shape probe.
                    // The factory already sets it; retain this for the raw-CG variant.
                    event.setIntegerValueField(CGEventField(rawValue: 51)!, value: Int64(window.windowID))
                    event.setIntegerValueField(.eventTargetUnixProcessID, value: Int64(app.processIdentifier))
                    event.setIntegerValueField(.mouseEventWindowUnderMousePointer, value: Int64(window.windowID))
                    event.setIntegerValueField(.mouseEventWindowUnderMousePointerThatCanHandleThisEvent, value: Int64(window.windowID))
                    event.setIntegerValueField(.mouseEventClickState, value: 1)
                    event.postToPid(app.processIdentifier)
                    try await Task.sleep(for: .milliseconds(command == "drag" ? 20 : 40))
                }
            } else if command == "spotlight" || command == "home" {
                for down in [true, false] {
                    guard let event = CGEvent(keyboardEventSource: source, virtualKey: command == "home" ? 18 : 20, keyDown: down) else { failure("Cannot create shortcut event") }
                    event.flags = .maskCommand
                    event.postToPid(app.processIdentifier)
                }
            } else {
                guard args.contains("--field-ready") else { failure("Focus a disposable phone field first; pass --field-ready") }
                if args.contains("--keycodes") {
                    // Fixed physical ANSI keys spelling phoneuse-probe; no clipboard or Unicode payload.
                    for key: CGKeyCode in [35, 4, 31, 45, 14, 32, 1, 14, 27, 35, 15, 31, 11, 14] {
                        for down in [true, false] {
                            guard let event = CGEvent(keyboardEventSource: source, virtualKey: key, keyDown: down) else { failure("Cannot create keyboard event") }
                            event.flags = []
                            event.postToPid(app.processIdentifier)
                        }
                        try await Task.sleep(for: .milliseconds(40))
                    }
                    emit(["type": "input_dispatched", "before": before, "after": desktop(),
                          "phone_effect": "unverified", "mechanism": "CGEvent.postToPid physical keycodes"])
                    return
                }
                // Fixed benign text; no clipboard changes or arbitrary input from a model.
                let units = Array("phoneuse-probe".utf16)
                for down in [true, false] {
                    guard let event = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: down) else { failure("Cannot create keyboard event") }
                    event.flags = []
                    units.withUnsafeBufferPointer { event.keyboardSetUnicodeString(stringLength: units.count, unicodeString: $0.baseAddress!) }
                    event.postToPid(app.processIdentifier)
                }
            }
            try await Task.sleep(for: .milliseconds(300))
            emit(["type": "input_dispatched", "before": before, "after": desktop(),
                  "phone_effect": "unverified; inspect phone result separately", "mechanism": "CGEvent.postToPid",
                  "command": command, "background_shape": args.contains("--background-shape")])
        } catch { failure("Capture or probe failed: \(error.localizedDescription)") }
    }
}
