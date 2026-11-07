// Test entry point compiled with reviewed, pinned upstream protocol sources in /tmp.
// No application installation, no direct RSD peer, and no Mac input synthesis.
import Foundation

enum DeviceResolver {
    static func udid(for value: String?) throws -> String {
        guard let value, value.count >= 24 else { throw ProbeError.invalidRequest }
        return value
    }
}
enum ProbeError: Error { case invalidRequest }

func asciiKey(_ value: UInt8) -> (UInt8, Bool)? {
    if (97...122).contains(value) { return (value - 97 + 4, false) }
    if (65...90).contains(value) { return (value - 65 + 4, true) }
    if (49...57).contains(value) { return (value - 49 + 0x1e, false) }
    if value == 48 { return (0x27, false) }
    if value == 32 { return (0x2c, false) }
    let plain: [UInt8: UInt8] = [45:0x2d,61:0x2e,91:0x2f,93:0x30,92:0x31,
        59:0x33,39:0x34,96:0x35,44:0x36,46:0x37,47:0x38]
    let shifted: [UInt8: UInt8] = [33:0x1e,64:0x1f,35:0x20,36:0x21,37:0x22,
        94:0x23,38:0x24,42:0x25,40:0x26,41:0x27,95:0x2d,43:0x2e,123:0x2f,
        125:0x30,124:0x31,58:0x33,34:0x34,126:0x35,60:0x36,62:0x37,63:0x38]
    if let code = plain[value] { return (code, false) }
    if let code = shifted[value] { return (code, true) }
    return nil
}

@main struct CoreDeviceHIDProbe {
    static func main() {
        setbuf(stdout, nil)
        DispatchQueue.global().asyncAfter(deadline: .now() + 25) { exit(2) }
        do {
            guard CommandLine.arguments.contains("--send"),
                  let payload = try JSONSerialization.jsonObject(with: FileHandle.standardInput.readDataToEndOfFile()) as? [String: Any],
                  let udid = payload["udid"] as? String,
                  let operation = payload["operation"] as? String else { throw ProbeError.invalidRequest }
            // Validate the ENTIRE text before opening services or sending the first key.
            let text = payload["text"] as? String ?? "phoneuse-probe"
            let keys = text.utf8.compactMap(asciiKey)
            if operation == "text" {
                guard text.utf8.count <= 256, keys.count == text.utf8.count,
                      payload["field_ready"] as? Bool == true else { throw ProbeError.invalidRequest }
            }
            let rsd = try RemoteServiceDiscovery(udid: udid)
            defer { rsd.close() }
            if let target = payload["digitizer_target"] as? Int {
                guard (0...10).contains(target), ["tap", "swipe"].contains(operation),
                      let x = payload["x"] as? Double, let y = payload["y"] as? Double,
                      [x,y].allSatisfy({ $0.isFinite && (0...1).contains($0) }) else { throw ProbeError.invalidRequest }
                let digitizer = try rsd.connect(to: "com.apple.coredevice.hid.indigo")
                defer { digitizer.close() }
                func send(_ kind: UInt64, _ px: Double, _ py: Double) throws {
                    try digitizer.sendRequest([
                        "featureIdentifier": .string("com.apple.coredevice.feature.remote.hid.digitizer"),
                        "messageType": .string("IndigoDigitizerEvent"),
                        "payload": .dictionary(["pointOne": .dictionary(["x": .double(px), "y": .double(py)]),
                            "eventType": .uint64(kind), "edge": .uint64(0), "target": .uint64(UInt64(target))])])
                }
                try send(0, x, y)
                if operation == "swipe" {
                    guard let x2 = payload["x2"] as? Double, let y2 = payload["y2"] as? Double,
                          [x2,y2].allSatisfy({ $0.isFinite && (0...1).contains($0) }) else { throw ProbeError.invalidRequest }
                    for step in 1...20 {
                        let t = Double(step) / 20
                        try send(1, x + (x2-x)*t, y + (y2-y)*t)
                        Thread.sleep(forTimeInterval: 0.025)
                    }
                    try send(2, x2, y2)
                } else {
                    Thread.sleep(forTimeInterval: 0.1)
                    try send(2, x, y)
                }
                try digitizer.ping()
                print("{\"type\":\"direct_hid\",\"transport_flushed\":true,\"mechanism\":\"indigo\",\"phone_effect\":\"unverified\"}")
                return
            }
            if let display = payload["register_display"] as? String {
                guard ["tap", "swipe"].contains(operation),
                      let surface = payload["touch_surface"] as? Int, (258...511).contains(surface),
                      let x = payload["x"] as? Double, let y = payload["y"] as? Double,
                      [x,y].allSatisfy({ $0.isFinite && (0...1).contains($0) }) else { throw ProbeError.invalidRequest }
                let connection = try rsd.connect(to: "com.apple.coredevice.hid.universalhidservice")
                defer { connection.close() }
                func request(_ body: [String: XPCObject]) -> [String: XPCObject] {
                    ["featureIdentifier": .string("com.apple.coredevice.feature.remote.universalhidservice"),
                     "messageType": .string("Request"), "payload": .dictionary(body)]
                }
                let descriptor: [String: XPCObject] = ["_CoreDevice_codablePropertyStorage": .dictionary([
                    "_ServiceID": .dictionary(["uint": .uint64(UInt64(surface))]),
                    "Product": .dictionary(["string": .string("PhoneUse temporary wireless touch")]),
                    "Built-In": .dictionary(["bool": .bool(true)]),
                    "DisplayID": .dictionary(["string": .string(display)]),
                    "DeviceUsagePairs": .dictionary(["array": .array([.dictionary(["dictionary": .dictionary([
                        "DeviceUsagePage": .dictionary(["int": .int64(13)]),
                        "DeviceUsage": .dictionary(["int": .int64(4)])])])])])])]
                let created = try connection.sendReceive(request(["createService": .dictionary(["_0": .dictionary(descriptor)])]))
                guard created["serviceID"]?.intValue == surface else { throw ProbeError.invalidRequest }
                defer {
                    let removed = try? connection.sendReceive(request(["removeService": .dictionary(["_0": .uint64(UInt64(surface))])]))
                    print("{\"type\":\"temporary_surface_cleanup\",\"error_reply\":\(removed == nil || removed?["errorContainer"] != nil)}")
                }
                func send(_ down: Bool, _ px: Double, _ py: Double) throws {
                    let report = HIDService.touchReport(state: down ? 0xc2 : 0x02, x: Int(px*65535), y: Int(py*65535))
                    try connection.sendRequest(request(["send": .dictionary(["_0": .data(report), "_1": .uint64(UInt64(surface))])]))
                }
                let x2 = payload["x2"] as? Double ?? x, y2 = payload["y2"] as? Double ?? y
                guard [x2,y2].allSatisfy({ $0.isFinite && (0...1).contains($0) }) else { throw ProbeError.invalidRequest }
                let steps = operation == "swipe" ? 30 : 4
                for step in 0...steps {
                    let t = Double(step)/Double(steps)
                    try send(true, x+(x2-x)*t, y+(y2-y)*t)
                    Thread.sleep(forTimeInterval: 0.02)
                }
                try send(false, x2, y2)
                try connection.ping()
                Thread.sleep(forTimeInterval: 0.5)
                print("{\"type\":\"temporary_surface\",\"created\":true,\"phone_effect\":\"unverified\"}")
                return
            }
            let hid = try HIDService(rsd: rsd)
            defer { hid.close() }
            let touchSurface = UInt64(payload["touch_surface"] as? Int ?? 257)
            switch operation {
            case "key":
                let keys: [String: UInt8] = ["tab": 0x2b, "space": 0x2c, "escape": 0x29,
                    "up": 0x52, "down": 0x51, "left": 0x50, "right": 0x4f, "delete": 0x2a,
                    "page-down": 0x4e, "page-up": 0x4b]
                guard let name = payload["key"] as? String, let usage = keys[name] else { throw ProbeError.invalidRequest }
                try hid.typeKey(usage, modifiers: payload["shift"] as? Bool == true ? [0xe1] : [])
            case "text":
                for (usage, shift) in keys {
                    try hid.typeKey(usage, modifiers: shift ? [0xe1] : [])
                }
            case "tap":
                guard let x = payload["x"] as? Double, let y = payload["y"] as? Double,
                      x.isFinite, y.isFinite, (0...1).contains(x), (0...1).contains(y) else { throw ProbeError.invalidRequest }
                if payload["touch_layout"] as? String == "minimal" {
                    // Alternate ordinary-contact layout documented by ipbtools/ipb.
                    // Isolates contact max/identity/timestamp differences from transport.
                    func report(_ down: Bool) -> Data {
                        var data = Data(repeating: 0, count: 58)
                        data[0] = 9; data[1] = 1; data[2] = 1; data[3] = down ? 0xc0 : 0
                        let px = UInt16((x * 65535).rounded()), py = UInt16((y * 65535).rounded())
                        data[4] = UInt8(px & 255); data[5] = UInt8(px >> 8)
                        data[6] = UInt8(py & 255); data[7] = UInt8(py >> 8)
                        return data
                    }
                    try hid.sendReport(surface: touchSurface, report: report(true))
                    Thread.sleep(forTimeInterval: 0.1)
                    try hid.sendReport(surface: touchSurface, report: report(false))
                } else {
                    for _ in 0..<4 {
                        try hid.sendReport(surface: touchSurface, report: HIDService.touchReport(state: 0xc2, x: Int(x * 65535), y: Int(y * 65535)))
                        Thread.sleep(forTimeInterval: 0.02)
                    }
                    try hid.sendReport(surface: touchSurface, report: HIDService.touchReport(state: 0x02, x: Int(x * 65535), y: Int(y * 65535)))
                }
            case "swipe":
                guard let x = payload["x"] as? Double, let y = payload["y"] as? Double,
                      let x2 = payload["x2"] as? Double, let y2 = payload["y2"] as? Double,
                      [x,y,x2,y2].allSatisfy({ $0.isFinite && (0...1).contains($0) }) else { throw ProbeError.invalidRequest }
                for step in 0...30 {
                    let t = Double(step) / 30
                    try hid.sendReport(surface: touchSurface, report: HIDService.touchReport(state: 0xc2,
                        x: Int((x + (x2-x)*t) * 65535), y: Int((y + (y2-y)*t) * 65535)))
                    Thread.sleep(forTimeInterval: 0.016)
                }
                try hid.sendReport(surface: touchSurface, report: HIDService.touchReport(state: 0x02, x: Int(x2 * 65535), y: Int(y2 * 65535)))
            case "home":
                try hid.pressButton(usagePage: 0x0c, usageCode: 0x40)
            default: throw ProbeError.invalidRequest
            }
            try hid.sync()
            print("{\"type\":\"direct_hid\",\"transport_flushed\":true,\"phone_effect\":\"unverified\"}")
        } catch {
            // Errors can contain device identifiers; do not print raw descriptions.
            print("{\"type\":\"direct_hid\",\"error\":\"connection_or_protocol_failure\"}")
            exit(1)
        }
    }
}
