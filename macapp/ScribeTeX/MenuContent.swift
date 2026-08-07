import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// The full menu-bar popover contents.
///
/// Layout, top → bottom:
///  - Setup guard (only when the repo is unset or Claude Code is missing)
///  - Status header (filed today/total, watcher on/off, inbox path)
///  - Start/Stop watcher toggle (install / uninstall)
///  - Needs-review submenu (from `needs-review`)
///  - Pick Inbox… (NSOpenPanel → set-inbox)
///  - Process a File… (NSOpenPanel → process), with drag-and-drop
///  - Locate ScribeTeX… / Refresh / Quit
struct MenuContent: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            header

            if model.needsRepo || (model.status?.claude_ok == false) {
                setupGuard
                Divider()
            }

            if let status = model.status {
                statusHeader(status)
                Divider()
                watcherToggle(status)
                needsReviewSection(status)
                Divider()
            } else if !model.needsRepo {
                Label("Loading status…", systemImage: "hourglass")
                    .foregroundStyle(.secondary)
                Divider()
            }

            inboxRow
            processRow
            compileRow
            correctRow
            Divider()
            footer
        }
        .padding(12)
        .frame(width: 320)
        .onDrop(of: [.fileURL], isTargeted: nil, perform: handleDrop)
        .onAppear { loadCourses() }
    }

    // MARK: - Compile

    @State private var courses: [String] = []

    private func loadCourses() {
        guard !model.needsRepo else { return }
        Task.detached(priority: .utility) {
            let list = (try? Bridge.knownCourses()) ?? []
            await MainActor.run { self.courses = list }
        }
    }

    @ViewBuilder
    private var compileRow: some View {
        if !courses.isEmpty {
            Menu {
                ForEach(courses, id: \.self) { course in
                    Menu(course) {
                        Button("Compile") {
                            model.perform { _ = try Bridge.compile(course: course) }
                        }
                        Button("Compile + auto-fix errors") {
                            model.perform { _ = try Bridge.build(course: course) }
                        }
                        Button("Open latest PDF") {
                            model.perform { _ = try Bridge.openPDF(course: course) }
                        }
                        Divider()
                        Button("Generate study guide") {
                            model.perform { _ = try Bridge.studyGuide(course: course) }
                        }
                        Button("Export flashcards (Anki TSV)") {
                            model.perform { _ = try Bridge.flashcards(course: course) }
                        }
                        Button("Verify (flag likely errors)") {
                            model.perform { _ = try Bridge.verify(course: course) }
                        }
                        Button("Caption figures") {
                            model.perform { _ = try Bridge.captionFigures(course: course) }
                        }
                    }
                }
            } label: {
                Label("Course tools…", systemImage: "doc.richtext")
            }
            .disabled(model.needsRepo || model.busy)
        }
    }

    @ViewBuilder
    private var correctRow: some View {
        if !courses.isEmpty {
            Button {
                CorrectionWindowController.shared.show(model: model)
            } label: {
                Label("Correct a note…", systemImage: "pencil.and.outline")
            }
            .disabled(model.needsRepo || model.busy)
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Image(systemName: "doc.text.fill").foregroundStyle(.tint)
            Text("ScribeTeX").font(.headline)
            Spacer()
            if model.busy {
                ProgressView().controlSize(.small)
            }
        }
    }

    // MARK: - Setup guard

    private var setupGuard: some View {
        VStack(alignment: .leading, spacing: 6) {
            if model.needsRepo {
                Label("Locate your ScribeTeX checkout to begin.",
                      systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                Button("Locate ScribeTeX…") { locateRepo() }
            }
            if model.status?.claude_ok == false {
                Label("Claude Code CLI + ScribeTeX plugin not detected.",
                      systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                Text("Install Claude Code and the ScribeTeX plugin, then Refresh. "
                     + "Filing requires the CLI to be on your PATH.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Status

    private func statusHeader(_ status: Status) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: status.watcher_running
                      ? "circle.fill" : "circle")
                    .foregroundStyle(status.watcher_running ? .green : .secondary)
                Text(status.watcher_running ? "Watcher running" : "Watcher stopped")
                    .fontWeight(.medium)
            }
            Text("Filed today: \(status.filed_today)   ·   Total: \(status.filed_total)")
                .font(.callout)
            if status.needs_review_count > 0 {
                Text("Needs review: \(status.needs_review_count)")
                    .font(.callout)
                    .foregroundStyle(.orange)
            }
            Text("Inbox: \(displayPath(status.inbox_dir))")
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
            if let err = model.lastError {
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(2)
            }
        }
    }

    // MARK: - Watcher toggle

    private func watcherToggle(_ status: Status) -> some View {
        Button {
            model.perform {
                _ = status.watcher_running ? try Bridge.uninstall() : try Bridge.install()
            }
        } label: {
            Label(status.watcher_running ? "Stop Watcher" : "Start Watcher",
                  systemImage: status.watcher_running ? "stop.circle" : "play.circle")
        }
        .disabled(model.busy)
    }

    // MARK: - Needs review

    @ViewBuilder
    private func needsReviewSection(_ status: Status) -> some View {
        if model.reviewItems.isEmpty {
            Label("No items need review", systemImage: "checkmark.circle")
                .foregroundStyle(.secondary)
        } else {
            Menu {
                ForEach(model.reviewItems) { item in
                    Button {
                        model.perform { _ = try Bridge.process(item.path) }
                    } label: {
                        VStack(alignment: .leading) {
                            Text(item.name)
                            if let reason = item.reason {
                                Text(reason).font(.caption)
                            }
                            Text(item.kind).font(.caption2)
                        }
                    }
                }
            } label: {
                Label("Needs Review (\(model.reviewItems.count))",
                      systemImage: "tray.full")
            }
            // Full editor: set course/section/subsection/date and re-file.
            // Open the window via the AppKit controller directly — SwiftUI's
            // openWindow no-ops from inside a MenuBarExtra popover on current
            // macOS, so we manage a real NSWindow instead.
            Button {
                ReviewWindowController.shared.show(model: model)
            } label: {
                Label("Review Notes…", systemImage: "square.and.pencil")
            }
        }
    }

    // MARK: - Inbox / process rows

    private var inboxRow: some View {
        Button {
            pickDirectory(title: "Choose your iPad inbox folder") { url in
                model.perform { _ = try Bridge.setInbox(url.path) }
            }
        } label: {
            Label("Pick Inbox…", systemImage: "folder")
        }
        .disabled(model.needsRepo || model.busy)
    }

    private var processRow: some View {
        Button {
            pickFile(title: "Choose a note to file") { url in
                model.perform { _ = try Bridge.process(url.path) }
            }
        } label: {
            Label("Process a File…", systemImage: "doc.badge.plus")
        }
        .disabled(model.needsRepo || model.busy)
    }

    // MARK: - Footer

    private var footer: some View {
        VStack(alignment: .leading, spacing: 4) {
            Button {
                locateRepo()
            } label: {
                Label(model.needsRepo ? "Locate ScribeTeX…" : "Change ScribeTeX Location…",
                      systemImage: "externaldrive")
            }
            Button {
                model.refresh()
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .keyboardShortcut("r")
            Button(role: .destructive) {
                NSApplication.shared.terminate(nil)
            } label: {
                Label("Quit ScribeTeX", systemImage: "power")
            }
            .keyboardShortcut("q")
        }
    }

    // MARK: - Drag and drop

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard !model.needsRepo, let provider = providers.first else { return false }
        _ = provider.loadObject(ofClass: URL.self) { url, _ in
            guard let url else { return }
            DispatchQueue.main.async {
                model.perform { _ = try Bridge.process(url.path) }
            }
        }
        return true
    }

    // MARK: - Panels

    private func locateRepo() {
        pickDirectory(title: "Locate your ScribeTeX repository checkout") { url in
            Bridge.repoRoot = url.path
            model.refresh()
        }
    }

    private func pickDirectory(title: String, _ handler: @escaping (URL) -> Void) {
        let panel = NSOpenPanel()
        panel.message = title
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "Choose"
        if panel.runModal() == .OK, let url = panel.url {
            handler(url)
        }
    }

    private func pickFile(title: String, _ handler: @escaping (URL) -> Void) {
        let panel = NSOpenPanel()
        panel.message = title
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Process"
        if panel.runModal() == .OK, let url = panel.url {
            handler(url)
        }
    }

    // MARK: - Helpers

    private func displayPath(_ path: String) -> String {
        (path as NSString).abbreviatingWithTildeInPath
    }
}
