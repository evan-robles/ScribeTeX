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
}

struct ReviewList: Codable { let ok: Bool; let items: [ReviewItem] }
struct ActionResult: Codable { let ok: Bool; let watcher_running: Bool? ; let error: String? }
