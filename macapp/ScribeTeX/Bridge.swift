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
        let pipe = Pipe(); p.standardOutput = pipe
        try p.run(); p.waitUntilExit()
        return pipe.fileHandleForReading.readDataToEndOfFile()
    }

    // Convenience wrappers naming each appcli command:
    static func status() throws -> Status { try JSONDecoder().decode(Status.self, from: run(["status"])) }
    static func needsReview() throws -> ReviewList { try JSONDecoder().decode(ReviewList.self, from: run(["needs-review"])) }
    static func setInbox(_ path: String) throws -> Data { try run(["set-inbox", "--path", path]) }
    static func process(_ path: String) throws -> Data { try run(["process", "--path", path]) }
    static func install() throws -> Data { try run(["install"]) }
    static func uninstall() throws -> Data { try run(["uninstall"]) }
}

enum BridgeError: Error { case noRepo }
