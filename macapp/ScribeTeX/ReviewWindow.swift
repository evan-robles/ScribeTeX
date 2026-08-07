import SwiftUI

/// A dedicated window listing every parked note (`needsReview`) with an editable
/// routing form. For each item the user confirms/corrects the course, section,
/// subsection, and date, then **Re-file**s it (which re-transcribes the note via
/// Claude — slow, spends tokens) or **Discard**s it from the queue.
///
/// On a successful action the model refreshes and the just-handled row drops out
/// of `model.reviewItems`.
struct ReviewWindow: View {
    @ObservedObject var model: AppModel

    /// Courses that already exist on disk, loaded once from `known-courses`.
    @State private var courses: [String] = []
    @State private var coursesError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            content
        }
        .frame(minWidth: 460, minHeight: 320)
        .task { await loadCourses() }
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Image(systemName: "square.and.pencil").foregroundStyle(.tint)
            Text("Review Notes").font(.headline)
            Spacer()
            if model.busy { ProgressView().controlSize(.small) }
            Button {
                model.refresh()
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(model.busy)
        }
        .padding(12)
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if model.needsRepo {
            emptyState("Locate your ScribeTeX checkout first.",
                       systemImage: "exclamationmark.triangle.fill")
        } else if model.reviewItems.isEmpty {
            emptyState("Nothing to review — all notes are filed.",
                       systemImage: "checkmark.circle")
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if let coursesError {
                        Text("Could not load courses: \(coursesError)")
                            .font(.caption)
                            .foregroundStyle(.orange)
                            .padding(.horizontal, 12)
                    }
                    ForEach(model.reviewItems) { item in
                        ReviewItemForm(model: model, item: item, courses: courses)
                        Divider()
                    }
                }
                .padding(.vertical, 12)
            }
            if let err = model.lastError {
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .padding(12)
            }
        }
    }

    private func emptyState(_ text: String, systemImage: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: systemImage)
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text(text).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(24)
    }

    // MARK: - Data

    private func loadCourses() async {
        // Bridge.knownCourses() is a blocking Process call; run it off the main
        // actor and only bring back Sendable values ([String] / String).
        let result: Result<[String], Error> = await Task.detached(priority: .userInitiated) {
            do { return .success(try Bridge.knownCourses()) }
            catch { return .failure(error) }
        }.value
        switch result {
        case .success(let list):
            courses = list
            coursesError = nil
        case .failure(let error):
            coursesError = AppModel.describe(error)
        }
    }
}

/// The per-note editable form. Holds its own edit state so typing in one row
/// does not disturb others.
private struct ReviewItemForm: View {
    @ObservedObject var model: AppModel
    let item: ReviewItem
    let courses: [String]

    /// Sentinel picker tag meaning "type a brand-new course name".
    private static let newCourseTag = "\u{0000}__new__"

    @State private var courseSelection: String = ""
    @State private var newCourse: String = ""
    @State private var section: String = ""
    @State private var subsection: String = ""
    @State private var date: Date = Date()
    /// Set once the user edits any field, so a late-arriving course list can't
    /// clobber their input when we re-run prefill.
    @State private var userEdited = false
    /// Whether prefill has run against a NON-EMPTY course list yet. The first
    /// onAppear often fires before courses load (async), so the course picker
    /// would be seeded against []; we re-seed when courses arrive.
    @State private var prefilledWithCourses = false
    /// True while prefill() is mutating state, so its own writes aren't mistaken
    /// for user edits by the onChange handlers.
    @State private var prefilling = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Title + reason
            VStack(alignment: .leading, spacing: 2) {
                Text(item.name).font(.headline)
                if let reason = item.reason, !reason.isEmpty {
                    Text(reason).font(.caption).foregroundStyle(.secondary)
                }
                Text(item.kind).font(.caption2).foregroundStyle(.tertiary)
            }

            // Course picker (+ inline "New course…")
            HStack {
                Text("Course").frame(width: 90, alignment: .leading)
                Picker("Course", selection: $courseSelection) {
                    ForEach(courses, id: \.self) { course in
                        Text(course).tag(course)
                    }
                    Divider()
                    Text("New course…").tag(Self.newCourseTag)
                }
                .labelsHidden()
            }
            if courseSelection == Self.newCourseTag {
                HStack {
                    Text("").frame(width: 90)
                    TextField("New course name", text: $newCourse)
                        .textFieldStyle(.roundedBorder)
                }
            }

            labeledField("Section", text: $section,
                         placeholder: "blank → agent picks from the note")
            labeledField("Subsection", text: $subsection,
                         placeholder: "blank → agent picks from the note")

            HStack {
                Text("Date").frame(width: 90, alignment: .leading)
                DatePicker("Date", selection: $date, displayedComponents: .date)
                    .labelsHidden()
            }

            HStack {
                Button {
                    refile()
                } label: {
                    Label("Re-file", systemImage: "tray.and.arrow.down")
                }
                .disabled(model.busy || resolvedCourse.isEmpty)

                Button(role: .destructive) {
                    model.perform { _ = try Bridge.discard(path: item.path) }
                } label: {
                    Label("Discard", systemImage: "trash")
                }
                .disabled(model.busy)

                Spacer()
            }
            Text("Re-filing re-transcribes the note (spends tokens, ~2 min).")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 12)
        .onAppear(perform: prefill)
        // Courses load asynchronously; if the first prefill ran before they
        // arrived, re-seed once they do — unless the user has already edited.
        .onChange(of: courses) { _ in
            if !userEdited && !prefilledWithCourses { prefill() }
        }
        // Any manual edit locks out further auto-prefill (prefill's own writes
        // are excluded via the `prefilling` guard).
        .onChange(of: courseSelection) { _ in markEdited() }
        .onChange(of: newCourse) { _ in markEdited() }
        .onChange(of: section) { _ in markEdited() }
        .onChange(of: subsection) { _ in markEdited() }
        .onChange(of: date) { _ in markEdited() }
    }

    private func markEdited() {
        if !prefilling { userEdited = true }
    }

    private func labeledField(_ label: String, text: Binding<String>, placeholder: String) -> some View {
        HStack {
            Text(label).frame(width: 90, alignment: .leading)
            TextField(placeholder, text: text)
                .textFieldStyle(.roundedBorder)
        }
    }

    // MARK: - Behavior

    /// The course string to submit: either the picked existing course or the
    /// trimmed free-text new-course name.
    private var resolvedCourse: String {
        if courseSelection == Self.newCourseTag {
            return newCourse.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return courseSelection
    }

    /// Seed the form from the item's parked guesses (and today's date if none).
    /// Runs on appear and again once courses load (unless the user has edited),
    /// so a guessed course that already exists is SELECTED rather than offered as
    /// a new course — which otherwise created a duplicate course dir on re-file.
    private func prefill() {
        prefilling = true
        defer { prefilling = false }
        if let guess = item.course, !guess.isEmpty {
            if courses.contains(guess) {
                courseSelection = guess
            } else {
                courseSelection = Self.newCourseTag
                newCourse = guess
            }
        } else if let first = courses.first {
            courseSelection = first
        } else {
            courseSelection = Self.newCourseTag
        }
        section = item.section ?? ""
        subsection = item.subsection ?? ""
        date = Self.parseDate(item.date) ?? Date()
        prefilledWithCourses = !courses.isEmpty
    }

    private func refile() {
        // Snapshot the Sendable values before the actor hop; do not capture the
        // main-actor-isolated bindings inside the detached task.
        let path = item.path
        let course = resolvedCourse
        let sec = section.trimmingCharacters(in: .whitespacesAndNewlines)
        let sub = subsection.trimmingCharacters(in: .whitespacesAndNewlines)
        let dateString = Self.format(date)
        model.perform {
            _ = try Bridge.refile(path: path, course: course,
                                  section: sec, subsection: sub, date: dateString)
        }
    }

    // MARK: - Date helpers (yyyy-MM-dd, matching the bridge contract)

    private static func makeFormatter() -> DateFormatter {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone.current
        f.dateFormat = "yyyy-MM-dd"
        return f
    }

    private static func parseDate(_ string: String?) -> Date? {
        guard let string, !string.isEmpty else { return nil }
        return makeFormatter().date(from: string)
    }

    private static func format(_ date: Date) -> String {
        makeFormatter().string(from: date)
    }
}
