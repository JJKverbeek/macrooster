import AppKit
import Foundation

final class AppDelegate: NSObject, NSApplicationDelegate, NSUserNotificationCenterDelegate {
    private var terminateTask: DispatchWorkItem?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let center = NSUserNotificationCenter.default
        center.delegate = self

        if CommandLine.arguments.contains("--notify") {
            deliverNotification(from: center)
            scheduleTermination(after: 3)
            return
        }

        // Bij een klik op de melding start macOS deze app opnieuw.
        scheduleTermination(after: 8)
    }

    func userNotificationCenter(_ center: NSUserNotificationCenter, shouldPresent notification: NSUserNotification) -> Bool {
        true
    }

    func userNotificationCenter(_ center: NSUserNotificationCenter, didActivate notification: NSUserNotification) {
        openCalendar()
        NSApp.terminate(nil)
    }

    private func deliverNotification(from center: NSUserNotificationCenter) {
        guard
            let notifyIndex = CommandLine.arguments.firstIndex(of: "--notify"),
            CommandLine.arguments.count > notifyIndex + 3
        else {
            NSApp.terminate(nil)
            return
        }

        let notification = NSUserNotification()
        notification.title = CommandLine.arguments[notifyIndex + 1]
        notification.informativeText = CommandLine.arguments[notifyIndex + 2]
        let subtitle = CommandLine.arguments[notifyIndex + 3]
        if !subtitle.isEmpty {
            notification.subtitle = subtitle
        }
        notification.soundName = NSUserNotificationDefaultSoundName
        notification.userInfo = ["openCalendar": "1"]
        center.deliver(notification)
    }

    private func scheduleTermination(after seconds: TimeInterval) {
        terminateTask?.cancel()
        let task = DispatchWorkItem {
            NSApp.terminate(nil)
        }
        terminateTask = task
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: task)
    }

    private func openCalendar() {
        guard let appURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.iCal") else {
            if let fallbackURL = URL(string: "ical://") {
                NSWorkspace.shared.open(fallbackURL)
            }
            return
        }

        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = true
        NSWorkspace.shared.openApplication(at: appURL, configuration: configuration) { _, _ in }
    }
}

@main
struct MacRoosterNotifierMain {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.run()
    }
}
