import Foundation

enum Bridge {
    // The repo root is chosen by the user on first run and stored in UserDefaults.
    static var repoRoot: String? {
        get { UserDefaults.standard.string(forKey: "ScribeTeXRepoRoot") }
        set { UserDefaults.standard.set(newValue, forKey: "ScribeTeXRepoRoot") }
    }
    static var pythonBin: String {
        UserDefaults.standard.string(forKey: "ScribeTeXPython") ?? "/usr/bin/python3"
    }

    static func run(_ args: [String]) throws -> Data {
        guard let root = repoRoot else { throw BridgeError.noRepo }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: pythonBin)
        p.arguments = ["-m", "automation.appcli"] + args
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = "\(root):\(root)/src"
        p.environment = env
        p.currentDirectoryURL = URL(fileURLWithPath: root)
        let outPipe = Pipe(); p.standardOutput = outPipe
        let errPipe = Pipe(); p.standardError = errPipe
        try p.run()
        // Drain both pipes fully before waiting, so a child that fills one
        // pipe's buffer while we block on the other can't deadlock.
        let outData = outPipe.fileHandleForReading.readDataToEndOfFile()
        let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        if p.terminationStatus != 0 {
            var message = String(data: errData, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if message.isEmpty {
                // Fall back to stdout if the failure detail landed there.
                message = String(data: outData, encoding: .utf8)?
                    .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            }
            throw BridgeError.failed(code: p.terminationStatus, stderr: message)
        }
        return outData
    }

    /// Run an action command, decode its `ActionResult`, and surface a
    /// bridge-reported `ok == false` (with its `error` text) as a thrown error
    /// rather than a silent success.
    @discardableResult
    static func action(_ args: [String]) throws -> ActionResult {
        let result = try JSONDecoder().decode(ActionResult.self, from: run(args))
        guard result.ok else {
            throw BridgeError.notOK(result.error ?? "The bridge reported failure with no detail.")
        }
        return result
    }

    // Convenience wrappers naming each appcli command:
    static func status() throws -> Status { try JSONDecoder().decode(Status.self, from: run(["status"])) }
    static func needsReview() throws -> ReviewList { try JSONDecoder().decode(ReviewList.self, from: run(["needs-review"])) }
    @discardableResult
    static func setInbox(_ path: String) throws -> ActionResult { try action(["set-inbox", "--path", path]) }
    @discardableResult
    static func process(_ path: String) throws -> ActionResult { try action(["process", "--path", path]) }
    @discardableResult
    static func install() throws -> ActionResult { try action(["install"]) }
    @discardableResult
    static func uninstall() throws -> ActionResult { try action(["uninstall"]) }
}

enum BridgeError: LocalizedError {
    case noRepo
    case failed(code: Int32, stderr: String)
    case notOK(String)

    var errorDescription: String? {
        switch self {
        case .noRepo:
            return "ScribeTeX repo not located. Use ‘Locate ScribeTeX…’ first."
        case let .failed(code, stderr):
            return "Bridge exited \(code): \(stderr.isEmpty ? "no error output" : stderr)"
        case let .notOK(message):
            return message
        }
    }
}
