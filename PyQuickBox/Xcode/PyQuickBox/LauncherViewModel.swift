import SwiftUI
import Combine // 필수: @Published, ObservableObject 사용을 위해 필요

// MARK: - LauncherViewModel
class LauncherViewModel: ObservableObject {
    
    // --- 1. UI 바인딩 데이터 ---
    @Published var registeredFolders: [String] = [] {
        didSet {
            saveFolders()
            refreshScripts()
            restartMonitoring() // 폴더가 바뀌면 감시 대상도 재설정
        }
    }
    
    @Published var groupedScripts: [String: [ScriptItem]] = [:]
    @Published var categories: [String] = []
    @Published var iconSize: CGFloat = 80.0
    
    // --- 2. 설정값 (앱 껐다 켜도 유지됨) ---
    // 스크린샷에 있던 설정 기능들과 매핑됩니다.
    @AppStorage("defaultInterpreterPath") var defaultInterpreterPath: String = "/usr/bin/python3"
    @AppStorage("runInTerminal") var runInTerminal: Bool = false
    @AppStorage("closeAfterRun") var closeAfterRun: Bool = false
    @AppStorage("labelFontSize") var labelFontSize: Double = 12.0
    
    
    // [추가] 검색어 바인딩용 변수
        @Published var searchText: String = ""
        
        // [추가] 검색어에 따라 필터링된 카테고리 목록 반환
        var visibleCategories: [String] {
            // 검색어가 없으면 전체 표시
            if searchText.isEmpty { return categories }
            
            return categories.filter { category in
                // 1. 카테고리 이름이 검색어를 포함하거나
                if category.localizedCaseInsensitiveContains(searchText) { return true }
                
                // 2. 해당 카테고리 안의 스크립트 중 하나라도 검색어를 포함하면 그 카테고리를 표시
                let scripts = groupedScripts[category] ?? []
                return scripts.contains { $0.name.localizedCaseInsensitiveContains(searchText) }
            }
        }
        
        // [추가] 특정 카테고리 안에서 보여줄 스크립트 필터링
        func visibleScripts(in category: String) -> [ScriptItem] {
            let scripts = groupedScripts[category] ?? []
            
            // 검색어가 없거나, 카테고리 자체가 검색어에 걸리면 -> 전체 스크립트 표시
            if searchText.isEmpty || category.localizedCaseInsensitiveContains(searchText) {
                return scripts
            }
            
            // 카테고리 이름은 안 맞았지만 내부 파일명이 맞아서 들어온 경우 -> 맞는 파일만 표시
            return scripts.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
        }
    
    
    // 파일 감지 객체
    private let monitor = DirectoryMonitor()
    
    init() {
        loadFolders()
        refreshScripts()
        restartMonitoring()
    }
    
    // MARK: - Folder Management (폴더 추가/삭제)
    func addFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        
        if panel.runModal() == .OK, let url = panel.url {
            // 중복 방지
            if !registeredFolders.contains(url.path) {
                registeredFolders.append(url.path)
            }
        }
    }
    
    func removeFolder(at offsets: IndexSet) {
        registeredFolders.remove(atOffsets: offsets)
    }
    
    // [추가] 특정 경로의 폴더를 삭제하는 함수
        func removePath(_ path: String) {
            if let index = registeredFolders.firstIndex(of: path) {
                registeredFolders.remove(at: index)
            }
        }
    
    private func saveFolders() {
        UserDefaults.standard.set(registeredFolders, forKey: "RegisteredFolders")
    }
    
    private func loadFolders() {
        if let saved = UserDefaults.standard.array(forKey: "RegisteredFolders") as? [String] {
            registeredFolders = saved
        }
    }
    
    // MARK: - File Monitoring (파일 변경 감지)
    private func restartMonitoring() {
        monitor.startMonitoring(paths: registeredFolders) { [weak self] in
            print("File change detected. Refreshing list...")
            self?.refreshScripts()
        }
    }
    
    // MARK: - Script Scanning & Parsing (파일 검색 및 분석)
        func refreshScripts() {
            // 백그라운드 스레드에서 파일 스캔 수행 (UI 멈춤 방지)
            DispatchQueue.global(qos: .userInitiated).async {
                var newGrouped: [String: [ScriptItem]] = [:]
                var newCategories: Set<String> = []
                let fileManager = FileManager.default
                
                for folderPath in self.registeredFolders {
                    guard let items = try? fileManager.contentsOfDirectory(atPath: folderPath) else { continue }
                    
                    for item in items where item.hasSuffix(".py") {
                        let fullPath = (folderPath as NSString).appendingPathComponent(item)
                        let fileName = (item as NSString).deletingPathExtension
                        
                        // [아이콘 로직 변경]
                        // 1. icon 폴더 경로 정의 (스크립트 폴더/icon)
                        let iconFolder = (folderPath as NSString).appendingPathComponent("icon")
                        
                        // 2. 후보 경로들: 전용 아이콘 vs 기본 아이콘
                        let specificIconPath = (iconFolder as NSString).appendingPathComponent(fileName + ".png")
                        let defaultIconPath = (iconFolder as NSString).appendingPathComponent("default.png")
                        
                        var finalIconPath: String? = nil
                        
                        // 3. 우선순위 체크: 이름.png -> default.png -> 없음(nil)
                        if fileManager.fileExists(atPath: specificIconPath) {
                            finalIconPath = specificIconPath
                        } else if fileManager.fileExists(atPath: defaultIconPath) {
                            finalIconPath = defaultIconPath
                        }
                        // 둘 다 없으면 nil로 남겨둠 -> ScriptItem에서 시스템 아이콘 사용
                        
                        // 파일 내부 파싱 (#pqr 헤더)
                        let (category, specificInterpreter) = self.parsePyFileHeader(path: fullPath)
                        
                        let scriptItem = ScriptItem(
                            name: fileName,
                            path: fullPath,
                            category: category,
                            iconPath: finalIconPath, // 결정된 아이콘 경로
                            interpreterPath: specificInterpreter
                        )
                        
                        if newGrouped[category] == nil {
                            newGrouped[category] = []
                        }
                        newGrouped[category]?.append(scriptItem)
                        newCategories.insert(category)
                    }
                }
                
                // [정렬 로직 변경] "Uncategorized"를 맨 뒤로 보내기
                let sortedCategories = Array(newCategories).sorted { (lhs, rhs) -> Bool in
                    if lhs == "Uncategorized" { return false } // 왼쪽이 Uncategorized면 무조건 뒤로(false)
                    if rhs == "Uncategorized" { return true }  // 오른쪽이 Uncategorized면 무조건 앞으로(true)
                    return lhs < rhs // 그 외에는 가나다순 정렬
                }
                
                // UI 업데이트는 반드시 메인 스레드에서
                DispatchQueue.main.async {
                    self.groupedScripts = newGrouped
                    self.categories = sortedCategories
                }
            }
        }
    
    // 파이썬 파일 상단 주석 파싱 로직 (최종 수정 버전)
        private func parsePyFileHeader(path: String) -> (String, String?) {
            // 파일 읽기 실패 시 기본값 반환
            guard let content = try? String(contentsOfFile: path, encoding: .utf8) else {
                return ("Uncategorized", nil)
            }
            
            var category = "Uncategorized"
            var interpreter: String? = nil
            
            let lines = content.components(separatedBy: .newlines)
            
            // 성능을 위해 상단 10줄만 검사
            for line in lines.prefix(10) {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                
                // 1. '#pqr cat' 태그 우선 확인 (운영체제 무관 카테고리)
                // 예: #pqr cat "My Tools"
                if trimmed.starts(with: "#pqr cat") {
                    let catPattern = #"#pqr\s+cat\s+"([^"]+)""#
                    if let regex = try? NSRegularExpression(pattern: catPattern, options: []) {
                        let nsString = line as NSString
                        let results = regex.matches(in: line, options: [], range: NSRange(location: 0, length: nsString.length))
                        
                        if let match = results.first {
                            category = nsString.substring(with: match.range(at: 1))
                        }
                    }
                }
                
                // 2. '#pqr mac' 태그 확인 (기존 호환 및 인터프리터 경로)
                // 예: #pqr mac "My Tools" /usr/bin/python3
                // 예: #pqr mac terminal "My Tools"
                if trimmed.starts(with: "#pqr mac") {
                    // 중간에 terminal 같은 단어가 있든 없든 처리하는 유연한 패턴
                    let macPattern = #"#pqr\s+mac.*"([^"]+)"\s*(.*)"#
                    
                    if let regex = try? NSRegularExpression(pattern: macPattern, options: []) {
                        let nsString = line as NSString
                        let results = regex.matches(in: line, options: [], range: NSRange(location: 0, length: nsString.length))
                        
                        if let match = results.first {
                            // 만약 위에서 cat으로 카테고리를 못 잡았다면 여기서 가져옴
                            if category == "Uncategorized" {
                                category = nsString.substring(with: match.range(at: 1))
                            }
                            
                            // 뒤에 경로가 적혀있다면 인터프리터로 설정
                            if match.range(at: 2).length > 0 {
                                let rawPath = nsString.substring(with: match.range(at: 2)).trimmingCharacters(in: .whitespaces)
                                if !rawPath.isEmpty {
                                    interpreter = rawPath
                                }
                            }
                        }
                    }
                }
            }
            
            return (category, interpreter)
        }
    
    // MARK: - Execution Logic (실제 실행)
    func runScript(_ script: ScriptItem) {
        // 1. 사용할 인터프리터 결정 (스크립트 개별 설정 > 앱 전체 설정)
        let interpreter = script.interpreterPath ?? defaultInterpreterPath
        let scriptPath = script.path
        
        print("Attempting to run: \(script.name)")
        print("Interpreter: \(interpreter)")
        
        if runInTerminal {
            runInMacTerminal(interpreter: interpreter, scriptPath: scriptPath)
        } else {
            runInBackground(interpreter: interpreter, scriptPath: scriptPath)
        }
        
        // 실행 후 창 닫기 옵션
        if closeAfterRun {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                NSApplication.shared.terminate(nil)
            }
        }
    }
    
    // A. 터미널 앱을 열어서 실행 (AppleScript 사용) - 수정버전
        private func runInMacTerminal(interpreter: String, scriptPath: String) {
            // [수정 핵심] 쉘에서는 경로에 공백이 있을 수 있으니 작은따옴표(')로 감쌉니다.
            // 이렇게 하면 AppleScript의 큰따옴표(")와 충돌하지 않습니다.
            let command = "'\(interpreter)' '\(scriptPath)'"
            
            // 터미널 앱에 명령 전달
            let appleScriptSource = """
            tell application "Terminal"
                activate
                do script "\(command)"
            end tell
            """
            
            var error: NSDictionary?
            if let scriptObject = NSAppleScript(source: appleScriptSource) {
                scriptObject.executeAndReturnError(&error)
                if let error = error {
                    print("AppleScript Error: \(error)")
                }
            }
        }
    
    // B. 백그라운드 실행 (Process 사용 - 창 없이 실행 + 에러 출력 강화)
        private func runInBackground(interpreter: String, scriptPath: String) {
            let task = Process()
            task.executableURL = URL(fileURLWithPath: interpreter)
            task.arguments = [scriptPath]
            
            // 실행 환경변수 설정
            var env = ProcessInfo.processInfo.environment
            env["PYTHONUNBUFFERED"] = "1"
            // 맥에서 GUI 관련 파이썬 라이브러리 실행 시 필요한 설정
            env["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""
            task.environment = env
            
            // 표준 출력과 에러를 각각 따로 캡처
            let outPipe = Pipe()
            let errPipe = Pipe()
            task.standardOutput = outPipe
            task.standardError = errPipe
            
            do {
                print("🚀 Process Launching: \(interpreter) \(scriptPath)")
                try task.run()
                
                // 실행 결과를 콘솔에 출력 (비동기)
                outPipe.fileHandleForReading.readabilityHandler = { handle in
                    if let line = String(data: handle.availableData, encoding: .utf8), !line.isEmpty {
                        print("🔵 [STDOUT]: \(line.trimmingCharacters(in: .whitespacesAndNewlines))")
                    }
                }
                errPipe.fileHandleForReading.readabilityHandler = { handle in
                    if let line = String(data: handle.availableData, encoding: .utf8), !line.isEmpty {
                        print("🔴 [STDERR]: \(line.trimmingCharacters(in: .whitespacesAndNewlines))")
                    }
                }
                
            } catch {
                print("❌ Process Run Error: \(error)")
                print("Tip: App Sandbox가 켜져있거나 경로가 잘못되면 이 에러가 납니다.")
            }
        }
}
