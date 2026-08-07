import Foundation

/// A tiny lock-guarded bool shared between the watchdog thread and the caller,
/// so the timeout signal crosses threads without a data race.
final class TimeoutFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var _value = false
    var value: Bool {
        get { lock.lock(); defer { lock.unlock() }; return _value }
        set { lock.lock(); _value = newValue; lock.unlock() }
    }
}

enum Bridge {
    // The repo root is chosen by the user on first run and stored in UserDefaults.
    static var repoRoot: String? {
        get { UserDefaults.standard.string(forKey: "ScribeTeXRepoRoot") }
        set { UserDefaults.standard.set(newValue, forKey: "ScribeTeXRepoRoot") }
    }
    /// The Python interpreter used to run the bridge.
    ///
    /// Honors an explicit `ScribeTeXPython` UserDefaults override if set;
    /// otherwise auto-discovers a Python 3.11+ (needed for `tomllib`). Probes
    /// common install locations and falls back to whatever `python3` is on the
    /// login PATH. `/usr/bin/python3` is tried LAST because on many Macs it is
    /// an older stub (e.g. Xcode's 3.9) that lacks `tomllib`.
    static var pythonBin: String {
        if let override = UserDefaults.standard.string(forKey: "ScribeTeXPython"),
           !override.isEmpty {
            return override
        }
        // Memoize discovery: probing candidate interpreters spawns 1-4 `python -c`
        // subprocesses, and pythonBin is read on every bridge call (every 15s
        // poll). Cache the first successful result for the process lifetime.
        if let cached = _cachedPythonBin { return cached }
        let found = discoverPython() ?? "/usr/bin/python3"
        _cachedPythonBin = found
        return found
    }
    private static var _cachedPythonBin: String?

    /// The candidate interpreters, in preference order, ending with the PATH
    /// `python3` and the system stub.
    private static var pythonCandidates: [String] {
        [
            "/opt/homebrew/bin/python3",   // Apple-silicon Homebrew
            "/usr/local/bin/python3",      // Intel Homebrew
            "/opt/homebrew/Caskroom/miniforge/base/bin/python3",  // miniforge (arm)
            "/usr/bin/python3",            // system stub (often too old) — last
        ]
    }

    /// Return the first candidate that is Python >= 3.11, or a PATH-resolved
    /// `python3` if it is new enough; nil if none qualifies.
    private static func discoverPython() -> String? {
        for path in pythonCandidates where FileManager.default.isExecutableFile(atPath: path) {
            if isSupported(path) { return path }
        }
        // Fall back to whatever `python3` resolves to on the login PATH.
        if let viaPath = resolveOnPath("python3"), isSupported(viaPath) {
            return viaPath
        }
        return nil
    }

    /// Resolve a command on the user's login PATH via `/usr/bin/env`.
    private static func resolveOnPath(_ cmd: String) -> String? {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        p.arguments = ["which", cmd]
        let out = Pipe(); p.standardOutput = out
        p.standardError = Pipe()
        do {
            try p.run()
            let data = out.fileHandleForReading.readDataToEndOfFile()
            p.waitUntilExit()
            guard p.terminationStatus == 0 else { return nil }
            let line = String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return (line?.isEmpty == false) ? line : nil
        } catch { return nil }
    }

    /// True if the interpreter at `path` reports version >= 3.11.
    private static func isSupported(_ path: String) -> Bool {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: path)
        p.arguments = ["-c", "import sys; print(sys.version_info[:2] >= (3, 11))"]
        let out = Pipe(); p.standardOutput = out
        p.standardError = Pipe()
        do {
            try p.run()
            let data = out.fileHandleForReading.readDataToEndOfFile()
            p.waitUntilExit()
            let s = String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return p.terminationStatus == 0 && s == "True"
        } catch { return false }
    }

    /// Run the Python bridge. `timeout` bounds how long we wait; if the child
    /// exceeds it we terminate it and throw, so a hung bridge (e.g. a wedged
    /// Claude call) can never block a caller forever. Status polls use a short
    /// timeout; the multi-minute refile passes a long one.
    static func run(_ args: [String], timeout: TimeInterval = 30) throws -> Data {
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

        // Watchdog: terminate (then hard-kill) the process if it overruns.
        // Killing it closes the pipes, unblocking the reads below.
        let timedOut = TimeoutFlag()
        let watchdog = DispatchWorkItem {
            if p.isRunning {
                timedOut.value = true
                p.terminate()
                DispatchQueue.global().asyncAfter(deadline: .now() + 2) {
                    if p.isRunning { kill(p.processIdentifier, SIGKILL) }
                }
            }
        }
        DispatchQueue.global().asyncAfter(deadline: .now() + timeout, execute: watchdog)

        // Drain both pipes fully before waiting, so a child that fills one
        // pipe's buffer while we block on the other can't deadlock.
        let outData = outPipe.fileHandleForReading.readDataToEndOfFile()
        let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        watchdog.cancel()

        if timedOut.value {
            throw BridgeError.timedOut(seconds: timeout)
        }
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
    static func action(_ args: [String], timeout: TimeInterval = 30) throws -> ActionResult {
        let result = try JSONDecoder().decode(ActionResult.self, from: run(args, timeout: timeout))
        guard result.ok else {
            throw BridgeError.notOK(result.error ?? "The bridge reported failure with no detail.")
        }
        return result
    }

    // Long timeout for commands that shell out to Claude or the toolchain.
    private static let slowTimeout: TimeInterval = 1800

    // Convenience wrappers naming each appcli command:
    static func status() throws -> Status { try JSONDecoder().decode(Status.self, from: run(["status"])) }
    static func needsReview() throws -> ReviewList { try JSONDecoder().decode(ReviewList.self, from: run(["needs-review"])) }
    @discardableResult
    static func setInbox(_ path: String) throws -> ActionResult { try action(["set-inbox", "--path", path]) }
    @discardableResult
    static func process(_ path: String) throws -> ActionResult {
        try action(["process", "--path", path], timeout: slowTimeout)  // runs Claude
    }
    @discardableResult
    static func install() throws -> ActionResult { try action(["install"], timeout: 120) }
    @discardableResult
    static func uninstall() throws -> ActionResult { try action(["uninstall"], timeout: 120) }

    /// The course directory names that already exist, for the Review window's
    /// course picker.
    static func knownCourses() throws -> [String] {
        try JSONDecoder().decode(CoursesList.self, from: run(["known-courses"])).courses
    }

    /// Re-file a parked note with a user-corrected course/section/subsection/
    /// date. This re-transcribes the note (spends Claude tokens), so it is
    /// slow — run it inside `AppModel.perform`.
    @discardableResult
    static func refile(path: String, course: String, section: String,
                       subsection: String, date: String) throws -> ActionResult {
        try action(["refile", "--path", path, "--course", course,
                    "--section", section, "--subsection", subsection, "--date", date],
                   timeout: slowTimeout)  // re-transcribes via Claude (~minutes)
    }

    /// Drop a parked note from the review queue without filing it.
    @discardableResult
    static func discard(path: String) throws -> ActionResult {
        try action(["discard", "--path", path])
    }
}

enum BridgeError: LocalizedError {
    case noRepo
    case failed(code: Int32, stderr: String)
    case notOK(String)
    case timedOut(seconds: TimeInterval)

    var errorDescription: String? {
        switch self {
        case .noRepo:
            return "ScribeTeX repo not located. Use ‘Locate ScribeTeX…’ first."
        case let .failed(code, stderr):
            return "Bridge exited \(code): \(stderr.isEmpty ? "no error output" : stderr)"
        case let .notOK(message):
            return message
        case let .timedOut(seconds):
            return "The bridge timed out after \(Int(seconds))s and was stopped."
        }
    }
}
