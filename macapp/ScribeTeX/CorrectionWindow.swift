import SwiftUI
import AppKit

/// Opens the Correction window (AppKit-hosted, like ReviewWindowController) so a
/// menu-bar (LSUIElement) app can reliably show it.
@MainActor
final class CorrectionWindowController: NSObject, NSWindowDelegate {
    static let shared = CorrectionWindowController()
    private var window: NSWindow?

    func show(model: AppModel) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        if let window {
            window.makeKeyAndOrderFront(nil)
            return
        }
        let host = NSHostingController(rootView: CorrectionWindow(model: model))
        let win = NSWindow(contentViewController: host)
        win.title = "Correct a Note"
        win.styleMask = [.titled, .closable, .miniaturizable, .resizable]
        win.setContentSize(NSSize(width: 520, height: 460))
        win.isReleasedWhenClosed = false
        win.delegate = self
        win.center()
        window = win
        win.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ notification: Notification) {
        window = nil
        NSApp.setActivationPolicy(.accessory)
    }
}

/// Pick a course → a filed note → describe a fix in plain language → correct.
/// The agent edits ONLY that note's block (surgical), optionally re-reading the
/// original page images when the fix needs looking at the source.
struct CorrectionWindow: View {
    @ObservedObject var model: AppModel

    @State private var courses: [String] = []
    @State private var course: String = ""
    @State private var notes: [NoteRef] = []
    @State private var selectedNoteKey: String = ""
    @State private var instruction: String = ""
    @State private var reread: Bool = false
    @State private var loadError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "pencil.and.outline").foregroundStyle(.tint)
                Text("Correct a Note").font(.headline)
                Spacer()
                if model.busy { ProgressView().controlSize(.small) }
            }

            HStack {
                Text("Course").frame(width: 80, alignment: .leading)
                Picker("Course", selection: $course) {
                    Text("Choose…").tag("")
                    ForEach(courses, id: \.self) { Text($0).tag($0) }
                }.labelsHidden()
            }

            if !notes.isEmpty {
                HStack(alignment: .top) {
                    Text("Note").frame(width: 80, alignment: .leading)
                    Picker("Note", selection: $selectedNoteKey) {
                        Text("Choose…").tag("")
                        ForEach(notes) { n in
                            Text("\(n.date) — \(n.sections.first ?? "(untitled)")").tag(n.key)
                        }
                    }.labelsHidden()
                }
            } else if !course.isEmpty {
                Text("No filed notes in this course yet.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("What should change?").frame(alignment: .leading)
                TextEditor(text: $instruction)
                    .frame(minHeight: 90)
                    .overlay(RoundedRectangle(cornerRadius: 6)
                        .stroke(.secondary.opacity(0.3)))
            }

            Toggle("Re-read the original pages (for a mis-read symbol or wrong figure)",
                   isOn: $reread)
                .font(.caption)

            HStack {
                Button {
                    correct()
                } label: {
                    Label("Apply Correction", systemImage: "checkmark.circle")
                }
                .disabled(model.busy || course.isEmpty || selectedNoteKey.isEmpty
                          || instruction.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Spacer()
            }
            Text("Edits only the chosen note (spends tokens, ~1–2 min).")
                .font(.caption2).foregroundStyle(.secondary)

            if let loadError {
                Text(loadError).font(.caption).foregroundStyle(.orange)
            }
            if let err = model.lastError {
                Text(err).font(.caption).foregroundStyle(.red).lineLimit(3)
            }
            Spacer()
        }
        .padding(16)
        .task { await loadCourses() }
        .onChange(of: course) { _ in loadNotes() }
    }

    private func loadCourses() async {
        let result: Result<[String], Error> = await Task.detached(priority: .userInitiated) {
            do { return .success(try Bridge.knownCourses()) }
            catch { return .failure(error) }
        }.value
        switch result {
        case .success(let list): courses = list; loadError = nil
        case .failure(let e): loadError = AppModel.describe(e)
        }
    }

    private func loadNotes() {
        notes = []; selectedNoteKey = ""
        guard !course.isEmpty else { return }
        let c = course
        Task.detached(priority: .userInitiated) {
            let fetched = (try? Bridge.listNotes(course: c)) ?? []
            await MainActor.run { if self.course == c { self.notes = fetched } }
        }
    }

    private func correct() {
        let c = course, key = selectedNoteKey
        let text = instruction.trimmingCharacters(in: .whitespacesAndNewlines)
        let rr = reread
        model.perform("Correcting note in \(c)") {
            _ = try Bridge.correct(course: c, noteKey: key, instruction: text, reread: rr)
        }
    }
}
