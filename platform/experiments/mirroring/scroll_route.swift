// Isolated scroll delivery comparison. No activation, global posts or cursor APIs.
import AppKit
import ApplicationServices
import Darwin

func output(_ data: [String:Any]) {
    print(String(decoding: try! JSONSerialization.data(withJSONObject:data,options:.sortedKeys),as:UTF8.self))
}
func stop(_ message: String) -> Never { output(["error":message]); exit(1) }
func desktopState() -> [String:Any] {
    var focused: CFTypeRef?
    AXUIElementCopyAttributeValue(AXUIElementCreateSystemWide(),kAXFocusedApplicationAttribute as CFString,&focused)
    var pid:pid_t = -1
    if let focused { AXUIElementGetPid(focused as! AXUIElement,&pid) }
    if pid == -1 {
        for app in NSWorkspace.shared.runningApplications where app.activationPolicy == .regular {
            var front:CFTypeRef?
            AXUIElementCopyAttributeValue(AXUIElementCreateApplication(app.processIdentifier),kAXFrontmostAttribute as CFString,&front)
            if front as? Bool == true {pid=app.processIdentifier;break}
        }
    }
    let p=CGEvent(source:nil)?.location ?? .zero
    return ["foreground_pid":pid,"cursor":[p.x,p.y]]
}
let args=CommandLine.arguments
DispatchQueue.global().asyncAfter(deadline:.now()+20){exit(2)}
let switches:Set<String>=["--send","--allow-front","--skylight","--public","--private-fields","--public-fields",
    "--no-primer","--positive","--up","--pixel","--phased"]
var optionIndex=4
while optionIndex<args.count {
    let flag=args[optionIndex]
    if ["--ticks","--step"].contains(flag) {
        guard args.count>optionIndex+1 else {stop("Missing bounded option value")}
        optionIndex+=2
    } else {
        guard switches.contains(flag) else {stop("Unknown scroll option")}
        optionIndex+=1
    }
}
guard args.contains("--send"),args.count>=4,let wid=UInt32(args[1]),let x=Double(args[2]),let y=Double(args[3]),
      [x,y].allSatisfy({$0.isFinite && (0...1).contains($0)}),AXIsProcessTrusted() else {stop("Need --send, window ID, normalized x y and Accessibility")}
guard let app=NSRunningApplication.runningApplications(withBundleIdentifier:"com.apple.ScreenContinuity").first,
      let rows=CGWindowListCopyWindowInfo(.optionAll,kCGNullWindowID) as? [[String:Any]],
      let row=rows.first(where:{($0[kCGWindowNumber as String] as? UInt32)==wid && ($0[kCGWindowOwnerPID as String] as? Int32)==app.processIdentifier}),
      let bounds=row[kCGWindowBounds as String] as? NSDictionary,let rect=CGRect(dictionaryRepresentation:bounds),
      rect.width>100,rect.height>100 else {stop("Target Mirroring window missing")}
let before=desktopState()
guard let foreground=before["foreground_pid"] as? Int32,foreground>0 else {stop("Cannot measure foreground app")}
guard before["foreground_pid"] as? Int32 != app.processIdentifier || args.contains("--allow-front") else {stop("Focus a disposable Mac app first")}
guard let sky=dlopen("/System/Library/PrivateFrameworks/SkyLight.framework/SkyLight",RTLD_NOW),
      let locSym=dlsym(sky,"CGEventSetWindowLocation") else {stop("Required SkyLight symbols unavailable")}
typealias Post = @convention(c)(Int32,CGEvent)->Void
typealias Field = @convention(c)(CGEvent,UInt32,Int64)->Void
typealias Location = @convention(c)(CGEvent,CGPoint)->Void
let post=dlsym(sky,"SLEventPostToPid").map {unsafeBitCast($0,to:Post.self)}
let field=dlsym(sky,"SLEventSetIntegerValueField").map {unsafeBitCast($0,to:Field.self)}
let location=unsafeBitCast(locSym,to:Location.self)
let useSky=args.contains("--skylight") && !args.contains("--public")
if useSky && post == nil {stop("Private post unavailable")}
if args.contains("--private-fields") && field == nil {stop("Private field setter unavailable")}
func boundedOption(_ name:String,default fallback:Int,range:ClosedRange<Int>)->Int {
    guard let index=args.firstIndex(of:name) else {return fallback}
    guard args.count>index+1,let number=Int(args[index+1]),range.contains(number) else {stop("Invalid bounded scroll option")}
    return number
}
// Validate every option before the first event, including the primer.
let ticks=boundedOption("--ticks",default:12,range:1...60)
let step=boundedOption("--step",default:args.contains("--pixel") ? 40 : 4,range:1...120)
let point=CGPoint(x:rect.minX+x*rect.width,y:rect.minY+y*rect.height)
let local=CGPoint(x:x*rect.width,y:y*rect.height)
let group=Int64(DispatchTime.now().uptimeNanoseconds & 0x7fff_ffff)
func send(_ event:CGEvent,mouse:Bool=false) {
    event.location=point
    location(event,local)
    event.flags=[]
    func set(_ key:UInt32,_ value:Int64) {
        if args.contains("--private-fields") {
            guard let field else {stop("Private field setter unavailable")};field(event,key,value)
        } else {event.setIntegerValueField(CGEventField(rawValue:key)!,value:value)}
    }
    for key:UInt32 in [51,91,92] {set(key,Int64(wid))}
    set(40,Int64(app.processIdentifier))
    set(58,group)
    if mouse {set(0,2);set(1,0);set(3,0);set(7,3)}
    if useSky {guard let post else {stop("Private post unavailable")};post(app.processIdentifier,event)}
    else {event.postToPid(app.processIdentifier)}
}
if !args.contains("--no-primer") {
    guard let moved=NSEvent.mouseEvent(with:.mouseMoved,location:.zero,modifierFlags:[],timestamp:ProcessInfo.processInfo.systemUptime,
        windowNumber:Int(wid),context:nil,eventNumber:1,clickCount:0,pressure:0)?.cgEvent else {stop("Cannot create primer")}
    send(moved,mouse:true)
    Thread.sleep(forTimeInterval:0.03)
}
let positive=args.contains("--positive") || args.contains("--up")
for index in 0..<ticks {
    guard let source=CGEventSource(stateID:.hidSystemState),
          let event=CGEvent(scrollWheelEvent2Source:source,units:args.contains("--pixel") ? .pixel : .line,wheelCount:2,
              wheel1:Int32((positive ? 1 : -1)*step),wheel2:0,wheel3:0) else {stop("Cannot create scroll")}
    if args.contains("--phased") {
        event.setIntegerValueField(.scrollWheelEventIsContinuous,value:1)
        event.setIntegerValueField(.scrollWheelEventScrollPhase,value:index==0 ? 1 : index==ticks-1 ? 4 : 2)
    }
    send(event)
    Thread.sleep(forTimeInterval:0.03)
}
Thread.sleep(forTimeInterval:0.3)
output(["type":"scroll_route","route":useSky ? "skylight_pid" : "public_pid",
        "units":args.contains("--pixel") ? "pixel" : "line","positive":positive,"ticks":ticks,"step":step,
        "before":before,"after":desktopState(),"phone_effect":"unverified"])
