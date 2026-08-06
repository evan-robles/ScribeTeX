import SwiftUI
import AppKit
import UserNotifications

/// Observable store that owns the app's live view of the bridge state.
///
/// It polls `Bridge.status()` (and, lazily, `Bridge.needsReview()`) on a
/// background queue so the menu never blocks the main thread while the Python
/// bridge runs, then republishes results on the main actor for SwiftUI.
@MainActor
final class AppModel: ObservableObject {
    @Published var status: Status?
    @Published var reviewItems: [ReviewItem] = []
    @Published var lastError: String?
    /// True while a bridge invocation is in flight (drives the "Working…" row).
    @Published var busy: Bool = false
    /// Set when the user still needs to point the app at the repo checkout.
    @Published var needsRepo: Bool = Bridge.repoRoot == nil

    private var timer: Timer?
    /// Last observed `needs_review_count`, used to fire a notification only when
    /// the count *rises* (a new note landed in review), not on every poll.
    /// `nil` until the first successful status read, so the initial load does
    /// not spam a notification for a pre-existing backlog.
    private var lastReviewCount: Int?

    /// Begin periodic polling. Safe to call more than once (idempotent).
    func start(interval: TimeInterval = 15) {
        refresh()
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
    }

    /// Re-read status (and needs-review, when there is anything to review).
    func refresh() {
        needsRepo = Bridge.repoRoot == nil
        guard !needsRepo else {
            status = nil
            reviewItems = []
            return
        }
        Task.detached(priority: .userInitiated) {
            // Compute everything off the main actor, then apply in a single hop.
            // Only Sendable values (Status, [ReviewItem], String) cross the
            // boundary — never a non-Sendable Error.
            let fetched: Status?
            let items: [ReviewItem]
            let failure: String?
            do {
                let s = try Bridge.status()
                fetched = s
                items = s.needs_review_count > 0
                    ? ((try? Bridge.needsReview().items) ?? [])
                    : []
                failure = nil
            } catch {
                fetched = nil
                items = []
                failure = Self.describe(error)
            }
            await MainActor.run { self.apply(status: fetched, items: items, failure: failure) }
        }
    }

    /// Apply a refresh result on the main actor.
    private func apply(status: Status?, items: [ReviewItem], failure: String?) {
        if let failure {
            lastError = failure
            return
        }
        if let status {
            let newCount = status.needs_review_count
            // Fire only on a rise, and never on the very first read.
            if let previous = lastReviewCount, newCount > previous {
                notifyReviewNeeded(count: newCount)
            }
            lastReviewCount = newCount
        }
        self.status = status
        reviewItems = items
        lastError = nil
    }

    /// Post a local notification announcing that notes need review. Tapping it
    /// opens the Review window (see `NotificationDelegate`).
    private func notifyReviewNeeded(count: Int) {
        let content = UNMutableNotificationContent()
        content.title = "ScribeTeX"
        let noun = count == 1 ? "note needs" : "notes need"
        content.body = "\(count) ScribeTeX \(noun) review."
        content.sound = .default
        let request = UNNotificationRequest(
            identifier: "scribetex.needs-review",
            content: content,
            trigger: nil // deliver immediately
        )
        UNUserNotificationCenter.current().add(request)
    }

    /// Run a bridge action off the main thread, then refresh the UI.
    func perform(_ action: @escaping () throws -> Void) {
        busy = true
        Task.detached(priority: .userInitiated) {
            let failure: String?
            do {
                try action()
                failure = nil
            } catch {
                failure = Self.describe(error)
            }
            await MainActor.run { self.finish(failure: failure) }
        }
    }

    /// Apply an action's outcome on the main actor, then refresh.
    private func finish(failure: String?) {
        busy = false
        if let failure { lastError = failure }
        refresh()
    }

    nonisolated static func describe(_ error: Error) -> String {
        // BridgeError conforms to LocalizedError, so localizedDescription
        // carries the useful message (repo missing, nonzero exit + stderr,
        // or a bridge-reported ok==false error string).
        error.localizedDescription
    }
}

/// Shared bus between the AppKit notification-center delegate (which cannot
/// reach SwiftUI's `openWindow`) and the SwiftUI scene graph. When the user
/// taps a review notification, the delegate flips `openReviewRequested`; a tiny
/// observer view inside the MenuBarExtra reacts and calls `openWindow`.
@MainActor
final class NotificationRouter: ObservableObject {
    static let shared = NotificationRouter()
    @Published var openReviewRequested: Bool = false
}

/// UNUserNotificationCenter delegate: shows banners while the app is frontmost
/// and opens the Review window when a notification is tapped.
final class NotificationDelegate: NSObject, UNUserNotificationCenterDelegate {
    /// Show the banner even when ScribeTeX is the active app.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }

    /// User tapped the notification — bring the app forward and request the
    /// Review window.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        Task { @MainActor in
            NSApp.activate(ignoringOtherApps: true)
            NotificationRouter.shared.openReviewRequested = true
        }
        completionHandler()
    }
}

/// AppKit lifecycle shim: installs the notification-center delegate and requests
/// authorization once, at launch.
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let notificationDelegate = NotificationDelegate()

    func applicationDidFinishLaunching(_ notification: Notification) {
        let center = UNUserNotificationCenter.current()
        center.delegate = notificationDelegate
        center.requestAuthorization(options: [.alert, .sound]) { _, _ in
            // Result ignored: if the user declines, we simply do not post
            // banners; the in-app Review window still works from the menu.
        }
    }
}

@main
struct ScribeTeXApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var model = AppModel()
    @StateObject private var router = NotificationRouter.shared

    var body: some Scene {
        MenuBarExtra("ScribeTeX", systemImage: menuBarSymbol) {
            MenuContent(model: model)
                .onAppear { model.start() }
                .background(ReviewWindowOpener(router: router))
        }
        .menuBarExtraStyle(.window)

        // A dedicated window for reviewing/re-filing parked notes. Opened from
        // the "Review Notes…" menu row or by tapping a notification.
        Window("Review Notes", id: "review") {
            ReviewWindow(model: model)
        }
        .windowResizability(.contentSize)
    }

    /// Icon reflects at-a-glance health: filled when the watcher is running,
    /// an exclamation badge when setup is incomplete.
    private var menuBarSymbol: String {
        if model.needsRepo || (model.status?.claude_ok == false) {
            return "doc.text.magnifyingglass"
        }
        return (model.status?.watcher_running == true) ? "doc.text.fill" : "doc.text"
    }
}

/// Invisible helper that lives inside the SwiftUI scene so it has access to the
/// `openWindow` environment action, and drives it from the notification router.
private struct ReviewWindowOpener: View {
    @ObservedObject var router: NotificationRouter
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Color.clear
            .frame(width: 0, height: 0)
            .onChange(of: router.openReviewRequested) { requested in
                if requested {
                    openWindow(id: "review")
                    router.openReviewRequested = false
                }
            }
    }
}
