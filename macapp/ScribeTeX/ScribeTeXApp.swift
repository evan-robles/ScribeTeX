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
            do {
                let s = try Bridge.status()
                var items: [ReviewItem] = []
                if s.needs_review_count > 0 {
                    items = (try? Bridge.needsReview().items) ?? []
                }
                await MainActor.run {
                    self.status = s
                    self.reviewItems = items
                    self.lastError = nil
                }
            } catch {
                await MainActor.run {
                    self.lastError = Self.describe(error)
                }
            }
        }
    }

    /// Run a bridge action off the main thread, then refresh the UI.
    func perform(_ action: @escaping () throws -> Void) {
        busy = true
        Task.detached(priority: .userInitiated) {
            var failure: String?
            do { try action() } catch { failure = Self.describe(error) }
            await MainActor.run {
                self.busy = false
                if let failure { self.lastError = failure }
                self.refresh()
            }
        }
    }

    static func describe(_ error: Error) -> String {
        if case BridgeError.noRepo = error {
            return "ScribeTeX repo location is not set."
        }
        return error.localizedDescription
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
