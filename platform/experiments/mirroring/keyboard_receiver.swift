// Disposable receiver + simulated human typing. Global events are TEST STIMULUS ONLY;
// the phone helper still uses process-targeted input. No Return, clipboard, or user text logging.
import AppKit
import ApplicationServices

final class Receiver: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    let text = NSTextView()
    var prior: NSRunningApplication?
    let arguments = CommandLine.arguments
    var helper: String { arguments[1] }
    var targetWindow: String { arguments[2] }

    func applicationDidFinishLaunching(_ notification: Notification) {
        setbuf(stdout, nil)
        prior = NSWorkspace.shared.frontmostApplication
        let covering = arguments.contains("--cover-phone")
        window = NSWindow(contentRect: covering ? NSRect(x:900,y:50,width:500,height:800) : NSRect(x: 200, y: 180, width: 640, height: 400),
                          styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = "PhoneUse disposable keyboard routing experiment"
        text.frame = covering ? NSRect(x:10,y:10,width:480,height:780) : NSRect(x: 10, y: 10, width: 620, height: 380)
        text.font = .monospacedSystemFont(ofSize: 20, weight: .regular)
        text.isAutomaticQuoteSubstitutionEnabled = false
        text.isAutomaticSpellingCorrectionEnabled = false
        text.isAutomaticTextReplacementEnabled = false
        window.contentView?.addSubview(text)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        window.makeFirstResponder(text)
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { self.start() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 25) { self.finish() }
    }

    func topOwner() -> Int32? {
        let rows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
        // Global z-order across multiple monitors is not keyboard focus. Hit-test the
        // receiver center so an unrelated window on another display does not abort the baseline.
        guard let own = rows.first(where: { ($0[kCGWindowNumber as String] as? Int) == window.windowNumber }),
              let ownBounds = own[kCGWindowBounds as String] as? NSDictionary,
              let rect = CGRect(dictionaryRepresentation: ownBounds) else { return nil }
        let center = CGPoint(x: rect.midX, y: rect.midY)
        return rows.first {
            guard ($0[kCGWindowLayer as String] as? Int) == 0,
                  let bounds = $0[kCGWindowBounds as String] as? NSDictionary,
                  let candidate = CGRect(dictionaryRepresentation: bounds) else { return false }
            return candidate.contains(center)
        }?[kCGWindowOwnerPID as String] as? Int32
    }

    func simulateTyping() -> Bool {
        // Fixed physical keycodes for macsentinel. Refuse if another window covers this receiver.
        for key: CGKeyCode in [46, 0, 8, 1, 14, 45, 17, 34, 45, 14, 37] {
            guard topOwner() == ProcessInfo.processInfo.processIdentifier else { return false }
            for down in [true, false] {
                guard let event = CGEvent(keyboardEventSource: nil, virtualKey: key, keyDown: down) else { return false }
                event.flags = []
                event.post(tap: .cghidEventTap)
            }
            Thread.sleep(forTimeInterval: 0.08)
        }
        return true
    }

    func start() {
        guard AXIsProcessTrusted() else { print("{\"error\":\"Accessibility required\"}"); finish(); return }
        DispatchQueue.global().async {
            let baselineSent = self.simulateTyping()
            Thread.sleep(forTimeInterval: 0.4)
            DispatchQueue.main.async {
                let baselineExact = self.text.string == "macsentinel"
                let rows = CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]] ?? []
                func bounds(_ id:Int)->CGRect? {
                    guard let row=rows.first(where:{($0[kCGWindowNumber as String] as? Int)==id}),
                          let dictionary=row[kCGWindowBounds as String] as? NSDictionary else {return nil}
                    return CGRect(dictionaryRepresentation:dictionary)
                }
                let phoneCovered = bounds(Int(self.targetWindow) ?? -1).map { phone in bounds(self.window.windowNumber)?.contains(phone) == true } ?? false
                print("{\"type\":\"baseline\",\"events_sent\":\(baselineSent),\"receiver_exact\":\(baselineExact),\"phone_covered_by_receiver\":\(phoneCovered)}")
                guard baselineExact else { self.finish(); return }
                guard !self.arguments.contains("--cover-phone") || phoneCovered else { self.finish(); return }
                self.text.string = ""
                DispatchQueue.global().async {
                    let phone = Process()
                    let direct = self.arguments.contains("--direct-hid")
                    let backgroundClick = self.arguments.contains("--background-click")
                    let backgroundScroll = self.arguments.contains("--background-scroll")
                    if backgroundScroll {
                        phone.executableURL = URL(fileURLWithPath: self.helper)
                        phone.arguments = [self.targetWindow,"0.5","0.65","--send","--public"]
                    } else if backgroundClick {
                        phone.executableURL = URL(fileURLWithPath: self.helper)
                        phone.arguments = ["tap", "0.115", "0.142", "--window", self.targetWindow,
                            "--send", "--local-event", "--background-shape"]
                    } else if direct {
                        guard self.arguments.count == 5 else { DispatchQueue.main.async { self.finish() }; return }
                        phone.executableURL = URL(fileURLWithPath: "/usr/bin/env")
                        phone.arguments = ["python3", self.arguments[4], "text", "--raw-hid", self.helper, "--send", "--observed-mirror-field"]
                    } else {
                        phone.executableURL = URL(fileURLWithPath: self.helper)
                        let mode = self.arguments.contains("--key-record-only") ? "--key-record-only" : "--make-key"
                        phone.arguments = ["text", "--window", self.targetWindow, "--send", "--field-ready", "--keycodes", mode, "--allow-front"]
                    }
                    phone.standardOutput = FileHandle.nullDevice
                    phone.standardError = FileHandle.nullDevice
                    do { try phone.run() } catch {
                        print("{\"error\":\"Could not start phone probe\"}")
                        DispatchQueue.main.async { self.finish() }; return
                    }
                    // Overlap simulated desktop typing with phone input. No Enter or shortcuts.
                    let repetitions = direct || backgroundClick || backgroundScroll ? 3 : 1
                    var overlapSent = true
                    for _ in 0..<repetitions { overlapSent = self.simulateTyping() && overlapSent }
                    phone.waitUntilExit()
                    Thread.sleep(forTimeInterval: 0.4)
                    let afterSent = self.simulateTyping()
                    Thread.sleep(forTimeInterval: 0.5)
                    DispatchQueue.main.async {
                        let value = self.text.string
                        let result: [String: Any] = ["type": "routing_result", "overlap_events_sent": overlapSent,
                            "after_events_sent": afterSent, "phone_exit": phone.terminationStatus,
                            "receiver_exact": value == String(repeating: "macsentinel", count: repetitions + 1),
                            "expected_copies": repetitions + 1, "mechanism": direct ? "direct HID" : backgroundClick ? "background click" : backgroundScroll ? "background scroll" : "window events",
                            "sentinel_copies": value.components(separatedBy: "macsentinel").count - 1,
                            "phone_text_in_receiver": value.contains("phoneuse"), "received_length": value.count]
                        print(String(decoding: try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]), as: UTF8.self))
                        self.finish()
                    }
                }
            }
        }
    }

    func finish() {
        // Never persist the receiver's text; restore the previous app, if still running.
        prior?.activate(options: [.activateAllWindows])
        NSApp.terminate(nil)
    }
}

guard (3...5).contains(CommandLine.arguments.count) else {
    print("Usage: keyboard-receiver PATH_TO_MIRROR_PROBE WINDOW_ID [--key-record-only]"); exit(1)
}
let app = NSApplication.shared
app.setActivationPolicy(.regular)
let receiver = Receiver()
app.delegate = receiver
app.run()
