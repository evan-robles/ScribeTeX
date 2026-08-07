import Foundation

struct Status: Codable {
    let ok: Bool
    let watcher_running: Bool
    let inbox_dir: String
    let filed_today: Int
    let filed_total: Int
    let needs_review_count: Int
    let claude_ok: Bool
    let settle_seconds: Int
    let sweep_seconds: Int
}

struct ReviewItem: Codable, Identifiable {
    var id: String { path }
    let name: String
    let path: String
    let reason: String?
    let kind: String
    // Best-effort routing guesses parked in the `.review.json` sidecar; all
    // nullable because a note may land in review precisely because they could
    // not be inferred.
    let course: String?
    let section: String?
    let subsection: String?
    let date: String?
}

struct ReviewList: Codable { let ok: Bool; let items: [ReviewItem] }
/// Response of `known-courses`: the course directory names already on disk.
struct CoursesList: Codable { let ok: Bool; let courses: [String] }
struct ActionResult: Codable { let ok: Bool; let watcher_running: Bool? ; let error: String? }

/// A filed note, for the notes list + "Correct a note" picker.
struct NoteRef: Codable, Identifiable {
    var id: String { key }
    let key: String        // "DATE:filename-slug" (the correction key)
    let date: String
    let sections: [String] // \section titles inside this note's block
    let figures: Int
    let uncertain: Int
}
struct NotesList: Codable { let ok: Bool; let notes: [NoteRef] }

/// Course metadata for the sidebar + tab enablement (from `courses-info`).
struct CourseInfo: Codable, Identifiable {
    var id: String { name }
    let name: String
    let note_count: Int
    let needs_review: Int
    let has_pdf: Bool
    let pdf_path: String
    let has_guide: Bool
    let guide_pdf: String
    let flashcard_count: Int
}
struct CoursesInfoList: Codable { let ok: Bool; let courses: [CourseInfo] }

/// One flashcard (from `read-flashcards`), for the in-app deck. The flip-card
/// view navigates by index, so identity here is only for ForEach stability;
/// q+a is unique enough for a deck.
struct Flashcard: Codable, Identifiable {
    var id: String { q + "\u{0001}" + a }
    let q: String
    let a: String
}
struct FlashcardList: Codable { let ok: Bool; let cards: [Flashcard] }
