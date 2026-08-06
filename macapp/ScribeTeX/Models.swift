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
