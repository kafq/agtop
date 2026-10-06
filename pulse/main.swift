// agtop-pulse: draws a soft glow around a screen rectangle, then exits.
//
// Usage: agtop-pulse <left> <top> <right> <bottom> [hex-colour]
//
// The rectangle uses AppleScript window bounds: global coordinates with the
// origin at the top-left of the primary display. The helper converts them to
// AppKit coordinates (origin at the bottom-left of the primary display).
//
// The overlay window is transparent, ignores the mouse, and joins every
// Space, so it never takes focus from the window it highlights.

import AppKit

let arguments = CommandLine.arguments
guard arguments.count >= 5,
      let left = Double(arguments[1]),
      let top = Double(arguments[2]),
      let right = Double(arguments[3]),
      let bottom = Double(arguments[4]),
      right > left, bottom > top
else {
    FileHandle.standardError.write("usage: agtop-pulse left top right bottom [hex-colour]\n".data(using: .utf8)!)
    exit(64)
}

func colour(fromHex hex: String) -> NSColor? {
    let digits = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
    guard digits.count == 6, let value = UInt32(digits, radix: 16) else { return nil }
    return NSColor(
        srgbRed: CGFloat((value >> 16) & 0xFF) / 255,
        green: CGFloat((value >> 8) & 0xFF) / 255,
        blue: CGFloat(value & 0xFF) / 255,
        alpha: 1
    )
}

let glowColour = (arguments.count > 5 ? colour(fromHex: arguments[5]) : nil)
    ?? NSColor(srgbRed: 1.0, green: 0.18, blue: 0.56, alpha: 1)

/// Room around the window for the glow to spread into.
let spread: CGFloat = 60
/// Matches the rounded corners of macOS 26 windows closely enough.
let cornerRadius: CGFloat = 14
let duration: CFTimeInterval = 1.2

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

guard let primary = NSScreen.screens.first else { exit(1) }
let target = NSRect(
    x: left,
    y: primary.frame.maxY - bottom,
    width: right - left,
    height: bottom - top
)
let frame = target.insetBy(dx: -spread, dy: -spread)

let window = NSWindow(contentRect: frame, styleMask: .borderless, backing: .buffered, defer: false)
window.isOpaque = false
window.backgroundColor = .clear
window.hasShadow = false
window.ignoresMouseEvents = true
window.level = .floating
window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]

let view = NSView(frame: NSRect(origin: .zero, size: frame.size))
view.wantsLayer = true
window.contentView = view

// A thin ring with a wide shadow of the same colour. With no fill and no
// shadowPath, the shadow follows the ring only, so the glow stays outside
// the text area instead of washing over it.
let ring = CALayer()
ring.frame = view.bounds.insetBy(dx: spread, dy: spread)
ring.cornerRadius = cornerRadius
ring.borderWidth = 4
ring.borderColor = glowColour.cgColor
ring.shadowColor = glowColour.cgColor
ring.shadowOffset = .zero
ring.shadowRadius = 28
ring.shadowOpacity = 1
ring.opacity = 0
view.layer?.addSublayer(ring)

// A wider, fainter halo behind the ring makes the glow carry further.
let halo = CALayer()
halo.frame = ring.frame
halo.cornerRadius = cornerRadius
halo.borderWidth = 6
halo.borderColor = glowColour.withAlphaComponent(0.5).cgColor
halo.shadowColor = glowColour.cgColor
halo.shadowOffset = .zero
halo.shadowRadius = 52
halo.shadowOpacity = 0.9
halo.opacity = 0
view.layer?.insertSublayer(halo, below: ring)

window.orderFrontRegardless()

// Two full-strength breaths: rise, settle, rise again, fade out.
let pulse = CAKeyframeAnimation(keyPath: "opacity")
pulse.values = [0, 1, 0.25, 1, 0]
pulse.keyTimes = [0, 0.22, 0.48, 0.68, 1]
pulse.timingFunctions = Array(
    repeating: CAMediaTimingFunction(name: .easeInEaseOut),
    count: 4
)
pulse.duration = duration

CATransaction.begin()
CATransaction.setCompletionBlock { app.terminate(nil) }
ring.add(pulse, forKey: "pulse")
halo.add(pulse, forKey: "pulse")
CATransaction.commit()

// Safety net: never linger, even if the animation is dropped.
DispatchQueue.main.asyncAfter(deadline: .now() + duration + 1) { app.terminate(nil) }

app.run()
