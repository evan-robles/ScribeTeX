import SwiftUI

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
        self.status = status
        reviewItems = items
        lastError = nil
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

@main
struct ScribeTeXApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        MenuBarExtra("ScribeTeX", systemImage: menuBarSymbol) {
            MenuContent(model: model)
                .onAppear { model.start() }
        }
        .menuBarExtraStyle(.window)
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
