package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"image/color"
	"io/ioutil"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strings"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/driver/desktop" // Mouse interaction
	"fyne.io/fyne/v2/theme"
	"fyne.io/fyne/v2/widget"
	"github.com/fsnotify/fsnotify"
)

// --- 데이터 모델 ---
type ScriptItem struct {
	Name            string
	Path            string
	Category        string
	IconPath        string
	InterpDefault   string // #pqr ... (Legacy or fallback)
	InterpMac       string // #pqr mac
	InterpWin       string // #pqr win
	InterpUbuntu    string // #pqr ubuntu
	Terminal        bool   // #pqr terminal true
}

// --- 앱 설정 키 ---
const (
	KeyRegisteredFolders = "RegisteredFolders"
	KeyPythonPath        = "PythonPath"
	KeyIconSize          = "IconSize"
	KeyFontSize          = "FontSize"
)

// --- 메인 구조체 ---
type LauncherApp struct {
	App        fyne.App
	Window     fyne.Window
	ContentBox *fyne.Container // 메인 스크롤 영역

	// 데이터
	Scripts           map[string][]ScriptItem // 카테고리별 스크립트
	Categories        []string
	RegisteredFolders []string

	// 설정
	DefaultPythonPath string
	IconSize          float32
	FontSize          float32

	// 검색
	SearchText  string
	SearchEntry *widget.Entry

	// 파일 감지
	Watcher *fsnotify.Watcher

	// UI State
	CurrentCategory string
	Sidebar         *widget.List
	SidebarVisible  bool
	MainContent     *fyne.Container // 우측 컨텐츠 영역 참조 유지
	TopBar          *fyne.Container
}

func main() {
	myApp := app.NewWithID("com.pyquickbox.linux")
	myWindow := myApp.NewWindow("PyQuickBox v1.0.0")

	launcher := &LauncherApp{
		App:      myApp,
		Window:   myWindow,
		Scripts:  make(map[string][]ScriptItem),
		IconSize: 80, // 기본값
		FontSize: 12, // 기본값
	}

	// 1. 설정 불러오기
	launcher.loadPreferences()

	// 2. 파일 감지기 시작
	watcher, err := fsnotify.NewWatcher()
	if err == nil {
		launcher.Watcher = watcher
		go launcher.watchFolders()
	}

	// 3. UI 구성
	launcher.setupUI()

	// 4. 초기 스캔
	launcher.refreshScripts()

	myWindow.Resize(fyne.NewSize(800, 600))
	myWindow.ShowAndRun()
}

// --- UI 구성 ---
func (l *LauncherApp) setupUI() {
	// 1. Sidebar (좌측)
	l.Sidebar = widget.NewList(
		func() int {
			// All Apps + Categories
			return 1 + len(l.Categories)
		},
		func() fyne.CanvasObject {
			return container.NewHBox(widget.NewIcon(theme.FolderIcon()), widget.NewLabel("Template"))
		},
		func(i widget.ListItemID, o fyne.CanvasObject) {
			hbox := o.(*fyne.Container)
			icon := hbox.Objects[0].(*widget.Icon)
			label := hbox.Objects[1].(*widget.Label)

			if i == 0 { // Item: All Apps
				icon.SetResource(theme.GridIcon())
				label.SetText("All Apps")
				label.TextStyle = fyne.TextStyle{Bold: true} // Make All Apps bold for distinction
				return
			}
			
			// Categories
			catIndex := i - 1
			if catIndex >= 0 && catIndex < len(l.Categories) {
				icon.SetResource(theme.FolderIcon())
				label.SetText(l.Categories[catIndex])
				label.TextStyle = fyne.TextStyle{}
			}
		},
	)
	
	l.Sidebar.OnSelected = func(id widget.ListItemID) {
		if id == 0 {
			l.CurrentCategory = "All"
		} else {
			catIndex := id - 1
			if catIndex >= 0 && catIndex < len(l.Categories) {
				l.CurrentCategory = l.Categories[catIndex]
			}
		}
		l.updateGridUI()
	}

	// 2. Top Bar (우측 상단)
	// 사이드바 토글 버튼 (아이콘: Menu)
	toggleBtn := widget.NewButtonWithIcon("", theme.MenuIcon(), func() {
		l.SidebarVisible = !l.SidebarVisible
		l.refreshLayout()
	})

	titleLabel := widget.NewLabelWithStyle("PyQuickBox", fyne.TextAlignLeading, fyne.TextStyle{Bold: true})
	
	l.SearchEntry = widget.NewEntry()
	l.SearchEntry.SetPlaceHolder("검색...")
	l.SearchEntry.OnChanged = func(s string) {
		l.SearchText = s
		l.updateGridUI()
	}
	// 검색창 크기 고정 (GridWrap 사용)
	searchContainer := container.NewGridWrap(fyne.NewSize(200, 34), l.SearchEntry)
	
	// 슬라이더
	iconSlider := widget.NewSlider(60, 200)
	iconSlider.Value = float64(l.IconSize)
	var debounceTimer *time.Timer
	iconSlider.OnChanged = func(f float64) {
		if debounceTimer != nil {
			debounceTimer.Stop()
		}
		l.IconSize = float32(f)
		l.App.Preferences().SetFloat(KeyIconSize, float64(l.IconSize))
		
		debounceTimer = time.AfterFunc(150*time.Millisecond, func() {
			l.updateGridUI()
		})
	}
	// 슬라이더 크기 고정
	sliderContainer := container.NewGridWrap(fyne.NewSize(150, 34), iconSlider)
	
	settingsBtn := widget.NewButtonWithIcon("", theme.SettingsIcon(), func() {
		l.showSettingsDialog()
	})

	topRightControls := container.NewHBox(
		widget.NewIcon(theme.SearchIcon()), searchContainer,
		widget.NewIcon(theme.GridIcon()), sliderContainer,
		settingsBtn,
	)
	
	// titleLabel 왼쪽에 toggleBtn 배치
	topLeftControls := container.NewHBox(toggleBtn, titleLabel)
	
	l.TopBar = container.NewBorder(nil, nil, topLeftControls, topRightControls)

	// 3. Main Content (우측)
	l.ContentBox = container.NewVBox()
	scrollArea := container.NewVScroll(l.ContentBox)
	
	l.MainContent = container.NewBorder(container.NewPadded(l.TopBar), nil, nil, nil, container.NewPadded(scrollArea))

	// 4. 초기 상태 설정 및 레이아웃 적용
	l.CurrentCategory = "All"
	l.SidebarVisible = true
	l.Sidebar.Select(0)
	
	l.refreshLayout()
}

// 레이아웃 갱신 (사이드바 토글 처리)
func (l *LauncherApp) refreshLayout() {
	if l.SidebarVisible {
		// Split Layout
		split := container.NewHSplit(l.Sidebar, l.MainContent)
		split.Offset = 0.2 // 사이드바 비율 조정
		l.Window.SetContent(split)
	} else {
		// Only Main Content
		l.Window.SetContent(l.MainContent)
	}
}

// --- 그리드 UI 갱신 (핵심) ---
func (l *LauncherApp) updateGridUI() {
	l.ContentBox.Objects = nil // 기존 내용 초기화

	// 표시할 스크립트 목록 수집
	var displayScripts []ScriptItem

	if l.CurrentCategory == "All" || l.CurrentCategory == "" {
		// 모든 카테고리 보기
		for _, scripts := range l.Scripts {
			displayScripts = append(displayScripts, scripts...)
		}
	} else {
		// 특정 카테고리 보기
		displayScripts = l.Scripts[l.CurrentCategory]
	}

	// 정렬 (이름순)
	sort.Slice(displayScripts, func(i, j int) bool {
		return strings.ToLower(displayScripts[i].Name) < strings.ToLower(displayScripts[j].Name)
	})

	// 검색어 필터링
	var filteredScripts []ScriptItem
	if l.SearchText == "" {
		filteredScripts = displayScripts
	} else {
		for _, s := range displayScripts {
			if strings.Contains(strings.ToLower(s.Name), strings.ToLower(l.SearchText)) {
				filteredScripts = append(filteredScripts, s)
			}
		}
	}

	if len(filteredScripts) == 0 {
		l.ContentBox.Refresh()
		return
	}

	// 그리드 생성 (섹션 헤더 없이)
	// 텍스트 높이 계산
	// 아이콘 보호를 위해 여유 공간을 충분히 확보 (4.5배)
	textHeight := float32(l.FontSize) * 4.5
	
	// 아이콘 간격 넓히기: 아이콘 크기 + 40 (좌우 여백)
	itemWidth := l.IconSize + 40
	itemHeight := l.IconSize + textHeight + 20 // 아이콘 + 텍스트 + 여백
	
	itemSize := fyne.NewSize(itemWidth, itemHeight)
	grid := container.NewGridWrap(itemSize)

	for _, script := range filteredScripts {
		sw := NewScriptWidget(script, l)
		grid.Add(sw)
	}

	l.ContentBox.Add(grid)
	l.ContentBox.Refresh()
}

// 검색 필터링
func (l *LauncherApp) filterScripts(category string) []ScriptItem {
	scripts := l.Scripts[category]
	if l.SearchText == "" {
		return scripts
	}

	// 카테고리 이름이 매칭되면 전체 표시
	if strings.Contains(strings.ToLower(category), strings.ToLower(l.SearchText)) {
		return scripts
	}

	// 파일명 매칭 확인
	var filtered []ScriptItem
	for _, s := range scripts {
		if strings.Contains(strings.ToLower(s.Name), strings.ToLower(l.SearchText)) {
			filtered = append(filtered, s)
		}
	}
	return filtered
}

// --- 로직: 스크립트 스캔 ---
func (l *LauncherApp) refreshScripts() {
	newScripts := make(map[string][]ScriptItem)
	newCategories := make(map[string]bool)

	for _, folder := range l.RegisteredFolders {
		files, err := ioutil.ReadDir(folder)
		if err != nil {
			continue
		}

		iconFolder := filepath.Join(folder, "icon")

		for _, file := range files {
			if filepath.Ext(file.Name()) == ".py" {
				fullPath := filepath.Join(folder, file.Name())
				fileName := strings.TrimSuffix(file.Name(), ".py")

				// 아이콘 찾기
				var iconPath string
				specificIcon := filepath.Join(iconFolder, fileName+".png")
				defaultIcon := filepath.Join(iconFolder, "default.png")

				if _, err := os.Stat(specificIcon); err == nil {
					iconPath = specificIcon
				} else if _, err := os.Stat(defaultIcon); err == nil {
					iconPath = defaultIcon
				}

				// 파싱
				cat, iMac, iWin, iUbu, term, iDef := l.parseHeader(fullPath)

				item := ScriptItem{
					Name:          fileName,
					Path:          fullPath,
					Category:      cat,
					IconPath:      iconPath,
					InterpMac:     iMac,
					InterpWin:     iWin,
					InterpUbuntu:  iUbu,
					Terminal:      term,
					InterpDefault: iDef,
				}

				newScripts[cat] = append(newScripts[cat], item)
				newCategories[cat] = true
			}
		}
	}

	// 카테고리 정렬
	var sortedCats []string
	for k := range newCategories {
		sortedCats = append(sortedCats, k)
	}
	sort.Strings(sortedCats)

	// Uncategorized 맨 뒤로
	finalCats := []string{}
	hasUncat := false
	for _, c := range sortedCats {
		if c == "Uncategorized" {
			hasUncat = true
		} else {
			finalCats = append(finalCats, c)
		}
	}
	if hasUncat {
		finalCats = append(finalCats, "Uncategorized")
	}

	l.Scripts = newScripts
	l.Categories = finalCats

	// UI 갱신은 메인 스레드에서
	l.Sidebar.Refresh() // 사이드바 갱신
	l.updateGridUI()

	// 감시 폴더 업데이트
	if l.Watcher != nil {
		for _, f := range l.RegisteredFolders {
			l.Watcher.Add(f)
		}
	}
}

// 파일 헤더 파싱 (#pqr)
func (l *LauncherApp) parseHeader(path string) (string, string, string, string, bool, string) {
	file, err := os.Open(path)
	if err != nil {
		return "Uncategorized", "", "", "", false, ""
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	category := "Uncategorized"
	var interpDefault, interpMac, interpWin, interpUbuntu string
	var terminal bool

	lineCount := 0
	for scanner.Scan() {
		if lineCount > 15 { // 헤더 파싱 범위 약간 늘림
			break
		}
		line := strings.TrimSpace(scanner.Text())

		// #pqr cat "Category"
		if strings.HasPrefix(line, "#pqr cat") {
			re := regexp.MustCompile(`#pqr\s+cat\s+"([^"]+)"`)
			matches := re.FindStringSubmatch(line)
			if len(matches) > 1 {
				category = matches[1]
			}
		}

		// #pqr mac "Path"
		if strings.HasPrefix(line, "#pqr mac") {
			re := regexp.MustCompile(`#pqr\s+mac\s+"([^"]+)"`)
			matches := re.FindStringSubmatch(line)
			if len(matches) > 1 {
				interpMac = matches[1]
			}
		}

		// #pqr win "Path"
		if strings.HasPrefix(line, "#pqr win") {
			re := regexp.MustCompile(`#pqr\s+win\s+"([^"]+)"`)
			matches := re.FindStringSubmatch(line)
			if len(matches) > 1 {
				interpWin = matches[1]
			}
		}

		// #pqr ubuntu "Path"
		if strings.HasPrefix(line, "#pqr ubuntu") {
			re := regexp.MustCompile(`#pqr\s+ubuntu\s+"([^"]+)"`)
			matches := re.FindStringSubmatch(line)
			if len(matches) > 1 {
				interpUbuntu = matches[1]
			}
		}

		// #pqr terminal true
		if strings.HasPrefix(line, "#pqr terminal") {
			if strings.Contains(line, "true") {
				terminal = true
			}
		}

		// Legacy: #pqr linux ... or simple #pqr "Cat" "Interp"
		if strings.HasPrefix(line, "#pqr") && 
			!strings.HasPrefix(line, "#pqr cat") &&
			!strings.HasPrefix(line, "#pqr mac") &&
			!strings.HasPrefix(line, "#pqr win") &&
			!strings.HasPrefix(line, "#pqr ubuntu") &&
			!strings.HasPrefix(line, "#pqr terminal") {
			
			re := regexp.MustCompile(`#pqr\s+\w+.*"([^"]+)"\s*(.*)`)
			matches := re.FindStringSubmatch(line)
			if len(matches) > 1 {
				// 이미 카테고리가 설정되지 않았다면 (우선순위를 cat 태그에 둠)
				if category == "Uncategorized" {
					category = matches[1]
				}
				if len(matches) > 2 {
					interpDefault = strings.TrimSpace(matches[2])
				}
			}
		}
		lineCount++
	}
	return category, interpMac, interpWin, interpUbuntu, terminal, interpDefault
}

// --- 로직: 실행 ---
func (l *LauncherApp) runScript(s ScriptItem) {
	var python string

	// OS별 인터프리터 선택
	switch runtime.GOOS {
	case "darwin": // Mac
		if s.InterpMac != "" {
			python = s.InterpMac
		}
	case "windows":
		if s.InterpWin != "" {
			python = s.InterpWin
		}
	case "linux":
		if s.InterpUbuntu != "" {
			python = s.InterpUbuntu
		}
	}

	// 1순위: OS 전용, 2순위: Default(Legacy), 3순위: 앱 설정 기본값
	if python == "" {
		python = s.InterpDefault
	}
	if python == "" {
		python = l.DefaultPythonPath
	}
	// 마지막 보루
	if python == "" {
		if runtime.GOOS == "windows" {
			python = "python"
		} else {
			python = "/usr/bin/python3"
		}
	}

	fmt.Printf("Run Code: %s / Path: %s\n", s.Name, python)

	// 터미널 실행 여부 (단순 구현: 터미널을 열어서 실행하는 것은 OS별로 복잡하므로, 
	// 여기서는 터미널 플래그가 있으면 xterm 등을 사용하는 식으로 확장이 가능하나,
	// 일단 로그만 찍고 기본 실행으로 유지하되, 필요시 확장)
	// Mac의 경우 'open -a Terminal script' 식이나
	// Windows의 경우 'cmd /k ...' 식의 처리가 필요.
	// 사용자 요청은 단순히 "Terminal 창 켤지 여부" 이므로
	// 간단히 구현 시도:
	
	var cmd *exec.Cmd

	if s.Terminal {
		cmd = l.createTerminalCommand(python, s.Path)
	} else {
		cmd = exec.Command(python, s.Path)
	}

	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = os.Environ()
	cmd.Env = append(cmd.Env, "PYTHONUNBUFFERED=1")

	go func() {
		err := cmd.Run()
		if err != nil {
			fmt.Printf("Error running script: %v\n", err)
			dialog.ShowError(err, l.Window)
		}
	}()
}

func (l *LauncherApp) createTerminalCommand(python, scriptPath string) *exec.Cmd {
	switch runtime.GOOS {
	case "darwin":
		// Mac: osascript를 사용하여 터미널 열기 등은 복잡하므로,
		// 여기서는 'open' 명령어로 터미널에서 실행되도록 유도하거나
		// 단순히 user choice에 따라 xterm 등을 호출.
		// 가장 호환성 높은 방법: Terminal.app에 스크립트를 던짐.
		// 하지만 python 인터프리터를 지정해서 열기는 까다로움.
		// 대안: 새 창을 띄우는 open -a Terminal 사용 (인자 전달의 어려움 있음)
		// 여기서는 "open"을 사용하여 기본 연결된 프로그램으로 열거나,
		// apple script로 do script ... 수행.
		
		// 간단한 접근:
		script := fmt.Sprintf(`tell application "Terminal" to do script "%s %s"`, python, scriptPath)
		return exec.Command("osascript", "-e", script)
		
	case "windows":
		// cmd /k "python script.py"
		return exec.Command("cmd", "/C", "start", "cmd", "/k", python, scriptPath)
	case "linux":
		// x-terminal-emulator or gnome-terminal
		return exec.Command("x-terminal-emulator", "-e", fmt.Sprintf("%s %s", python, scriptPath))
	default:
		return exec.Command(python, scriptPath)
	}
}

// 파일 위치 열기
func (l *LauncherApp) openFileLocation(s ScriptItem) {
	dir := filepath.Dir(s.Path)
	switch runtime.GOOS {
	case "darwin":
		exec.Command("open", dir).Start()
	case "windows":
		exec.Command("explorer", dir).Start()
	case "linux":
		exec.Command("xdg-open", dir).Start()
	}
}

// --- 설정 및 데이터 관리 ---
func (l *LauncherApp) loadPreferences() {
	l.DefaultPythonPath = l.App.Preferences().StringWithFallback(KeyPythonPath, "/usr/bin/python3")
	l.IconSize = float32(l.App.Preferences().FloatWithFallback(KeyIconSize, 80))
	l.FontSize = float32(l.App.Preferences().FloatWithFallback(KeyFontSize, 12))

	foldersJson := l.App.Preferences().String(KeyRegisteredFolders)
	if foldersJson != "" {
		json.Unmarshal([]byte(foldersJson), &l.RegisteredFolders)
	}
}

func (l *LauncherApp) savePreferences() {
	l.App.Preferences().SetString(KeyPythonPath, l.DefaultPythonPath)
	l.App.Preferences().SetFloat(KeyIconSize, float64(l.IconSize))
	l.App.Preferences().SetFloat(KeyFontSize, float64(l.FontSize))

	data, _ := json.Marshal(l.RegisteredFolders)
	l.App.Preferences().SetString(KeyRegisteredFolders, string(data))
}

// 설정 다이얼로그
func (l *LauncherApp) showSettingsDialog() {
	// 파이썬 경로
	pythonEntry := widget.NewEntry()
	pythonEntry.SetText(l.DefaultPythonPath)

	pythonBtn := widget.NewButton("찾기", func() {
		dialog.ShowFileOpen(func(reader fyne.URIReadCloser, err error) {
			if err == nil && reader != nil {
				pythonEntry.SetText(reader.URI().Path())
			}
		}, l.Window)
	})
	
	// 폰트 크기 조절
	fontSlider := widget.NewSlider(10, 24) // 10 ~ 24
	fontSlider.Step = 1
	fontSlider.Value = float64(l.FontSize)
	fontLabel := widget.NewLabel(fmt.Sprintf("%.0f", fontSlider.Value))
	fontSlider.OnChanged = func(f float64) {
		l.FontSize = float32(f)
		fontLabel.SetText(fmt.Sprintf("%.0f", f))
	}
	
	fontContainer := container.NewBorder(nil, nil, nil, fontLabel, fontSlider)

	// 폴더 리스트
	folderList := widget.NewList(
		func() int { return len(l.RegisteredFolders) },
		func() fyne.CanvasObject {
			return container.NewBorder(nil, nil, nil, widget.NewButtonWithIcon("", theme.DeleteIcon(), nil), widget.NewLabel("template"))
		},
		func(i widget.ListItemID, o fyne.CanvasObject) {
			c := o.(*fyne.Container)
			label := c.Objects[0].(*widget.Label)
			btn := c.Objects[1].(*widget.Button)

			folder := l.RegisteredFolders[i]
			label.SetText(folder)

			btn.OnTapped = func() {
				// 삭제 로직
				l.RegisteredFolders = append(l.RegisteredFolders[:i], l.RegisteredFolders[i+1:]...)
				l.savePreferences()
				l.refreshScripts()
				l.Window.Content().Refresh()
			}
		},
	)
	folderScroll := container.NewVScroll(folderList)
	folderScroll.SetMinSize(fyne.NewSize(0, 200))

	addFolderBtn := widget.NewButtonWithIcon("폴더 추가", theme.ContentAddIcon(), func() {
		dialog.ShowFolderOpen(func(uri fyne.ListableURI, err error) {
			if err == nil && uri != nil {
				path := uri.Path()
				exists := false
				for _, f := range l.RegisteredFolders {
					if f == path {
						exists = true
						break
					}
				}
				if !exists {
					l.RegisteredFolders = append(l.RegisteredFolders, path)
					l.savePreferences()
					l.refreshScripts()
					folderList.Refresh()
				}
			}
		}, l.Window)
	})

	// 다이얼로그 내용 구성
	content := container.NewVBox(
		widget.NewLabelWithStyle("기본 파이썬 경로:", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		container.NewBorder(nil, nil, nil, pythonBtn, pythonEntry),
		widget.NewSeparator(),
		widget.NewLabelWithStyle("라벨 폰트 크기:", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		fontContainer,
		widget.NewSeparator(),
		widget.NewLabelWithStyle("등록된 폴더:", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		addFolderBtn,
		folderScroll,
	)

	d := dialog.NewCustom("환경 설정", "닫기", content, l.Window)
	d.Resize(fyne.NewSize(500, 600))

	d.SetOnClosed(func() {
		l.DefaultPythonPath = pythonEntry.Text
		l.savePreferences()
		l.refreshScripts() // 폰트 변경 반영을 위해 갱신 필요 (사실 updateGridUI만 해도 되지만 단순화)
	})

	d.Show()
}

// 속성 다이얼로그
func (l *LauncherApp) showPropertiesDialog(s ScriptItem) {
	catEntry := widget.NewEntry()
	catEntry.SetText(s.Category)

	macEntry := widget.NewEntry()
	macEntry.SetText(s.InterpMac)

	winEntry := widget.NewEntry()
	winEntry.SetText(s.InterpWin)

	ubuEntry := widget.NewEntry()
	ubuEntry.SetText(s.InterpUbuntu)
	
	termCheck := widget.NewCheck("터미널 창 열기", nil)
	termCheck.Checked = s.Terminal

	form := widget.NewForm(
		widget.NewFormItem("카테고리", catEntry),
		widget.NewFormItem("Mac 실행기", macEntry),
		widget.NewFormItem("Win 실행기", winEntry),
		widget.NewFormItem("Ubuntu 실행기", ubuEntry),
		widget.NewFormItem("", termCheck),
	)

	d := dialog.NewCustomConfirm("스크립트 속성", "저장", "취소", form, func(b bool) {
		if b {
			l.updateScriptMetadata(s, catEntry.Text, macEntry.Text, winEntry.Text, ubuEntry.Text, termCheck.Checked)
			l.refreshScripts()
		}
	}, l.Window)
	
	d.Resize(fyne.NewSize(500, 400))
	d.Show()
}

// 메타데이터 업데이트 (파일 쓰기)
func (l *LauncherApp) updateScriptMetadata(s ScriptItem, cat, mac, win, ubu string, term bool) {
	content, err := ioutil.ReadFile(s.Path)
	if err != nil {
		dialog.ShowError(err, l.Window)
		return
	}
	
	lines := strings.Split(string(content), "\n")
	var newLines []string
	
	// Shebang 보존 확인
	hasShebang := len(lines) > 0 && strings.HasPrefix(lines[0], "#!")
	if hasShebang {
		newLines = append(newLines, lines[0])
	}
	
	// 새 태그 생성
	newLines = append(newLines, fmt.Sprintf("#pqr cat \"%s\"", cat))
	if mac != "" { newLines = append(newLines, fmt.Sprintf("#pqr mac \"%s\"", mac)) }
	if win != "" { newLines = append(newLines, fmt.Sprintf("#pqr win \"%s\"", win)) }
	if ubu != "" { newLines = append(newLines, fmt.Sprintf("#pqr ubuntu \"%s\"", ubu)) }
	if term { newLines = append(newLines, "#pqr terminal true") }
	
	// 기존 내용 중 #pqr 태그 제거 (상단 20줄 이내)
	for i, line := range lines {
		if hasShebang && i == 0 {
			continue
		}
		
		isTag := false
		if i < 30 { // 30줄까지만 검사
			trim := strings.TrimSpace(line)
			if strings.HasPrefix(trim, "#pqr") {
				isTag = true
			}
		}
		
		if !isTag {
			newLines = append(newLines, line)
		}
	}
	
	err = ioutil.WriteFile(s.Path, []byte(strings.Join(newLines, "\n")), 0644)
	if err != nil {
		dialog.ShowError(err, l.Window)
	}


}

// 파일 감시
func (l *LauncherApp) watchFolders() {
	for {
		select {
		case event, ok := <-l.Watcher.Events:
			if !ok {
				return
			}
			if event.Op&fsnotify.Write == fsnotify.Write || event.Op&fsnotify.Create == fsnotify.Create || event.Op&fsnotify.Remove == fsnotify.Remove {
				time.Sleep(500 * time.Millisecond)
				l.refreshScripts()
			}
		case <-l.Watcher.Errors:
			return
		}
	}
}

// --- 커스텀 위젯: ScriptWidget ---
type ScriptWidget struct {
	widget.BaseWidget
	item ScriptItem
	app  *LauncherApp

	lastTap time.Time
	
	// UI Elements for manipulation
	background *canvas.Rectangle
	icon       *canvas.Image
}

func NewScriptWidget(item ScriptItem, app *LauncherApp) *ScriptWidget {
	w := &ScriptWidget{item: item, app: app}
	w.ExtendBaseWidget(w)
	return w
}

func (w *ScriptWidget) CreateRenderer() fyne.WidgetRenderer {
	// 배경 (Hover 효과용)
	w.background = canvas.NewRectangle(theme.HoverColor())
	w.background.FillColor = color.Transparent
	w.background.CornerRadius = 8 // 모던한 느낌을 위한 둥근 모서리

	// 아이콘
	if w.item.IconPath != "" {
		w.icon = canvas.NewImageFromFile(w.item.IconPath)
	} else {
		w.icon = canvas.NewImageFromResource(theme.FileIcon())
	}
	// Aspect Ratio 고정 (매우 중요)
	w.icon.FillMode = canvas.ImageFillContain
	w.icon.SetMinSize(fyne.NewSize(w.app.IconSize, w.app.IconSize))
	// 라벨 (RichText 사용 - 줄바꿈 지원)
	// RichText does not support arbitrary float size in struct safely in all versions.
	// But we can try to use standard size if float fails, or just rely on VBox layout.
	// User REALLY wants spacing and wrapping.
	// 라벨 (canvas.Text + Smart Wrapping)
	// Custom Font Size를 지원하기 위해 canvas.Text 사용.
	// 텍스트 래핑 헬퍼를 사용하여 줄별로 분리하고, 각 줄을 별도의 canvas.Text로 렌더링
	// canvas.Text는 개행 문자(\n)를 지원하지 않아 "다이아몬드(?)" 문자가 발생하므로 분리 필수.
	
	lines := wrapSmart(w.item.Name, w.app.FontSize, w.app.IconSize+30) // Width 약간 여유
	
	labelVBox := container.NewVBox()
	for _, line := range lines {
		txt := canvas.NewText(line, theme.ForegroundColor())
		txt.TextSize = w.app.FontSize
		txt.Alignment = fyne.TextAlignCenter
		labelVBox.Add(txt)
	}
	
	// 레이아웃: Border (Icon=Top, Label=Center)
	// Border Layout의 Top 영역은 컨텐츠의 MinSize만큼 우선 할당되므로
	// 라벨이 길어져도 아이콘 영역을 침범하지 않음 (아이콘 찌그러짐 방지)
	
	// 아이콘 컨테이너: 높이 고정 (IconSize) -> 센터 정렬
	// +20을 제거하고 정사각형을 강제함. Centering은 NewCenter가 담당.
	iconContainer := container.NewGridWrap(fyne.NewSize(w.app.IconSize, w.app.IconSize), w.icon)
	
	// 라벨 컨테이너 (위에서 생성한 VBox 사용)
	// Center 영역에 배치. VBox는 기본적으로 내용물만큼의 높이를 가짐.
	// container.NewCenter(labelVBox)를 사용하여 수직/수평 중앙 정렬? 
	// 아니면 그냥 labelVBox만 넣으면 Top align? (VBox packs from top)
	
	// Final Layout
	mainLayout := container.NewBorder(
		container.NewCenter(iconContainer), // Top
		nil, nil, nil,
		labelVBox, // Center
	)
	
	// Full stack
	content := container.NewMax(w.background, container.NewPadded(mainLayout))
	
	return widget.NewSimpleRenderer(content)
}

// Hoverable 인터페이스 구현
func (w *ScriptWidget) MouseIn(*desktop.MouseEvent) {
	w.background.FillColor = theme.HoverColor()
	w.background.Refresh()
}

func (w *ScriptWidget) MouseOut() {
	w.background.FillColor = color.Transparent
	w.background.Refresh()
}

func (w *ScriptWidget) MouseMoved(*desktop.MouseEvent) {}

func (w *ScriptWidget) Tapped(e *fyne.PointEvent) {
	// 더블 클릭 감지 (500ms)
	if time.Since(w.lastTap) < 500*time.Millisecond {
		w.animateLaunch()
		w.app.runScript(w.item)
		w.lastTap = time.Time{} // 초기화
	} else {
		w.lastTap = time.Now()
	}
}

func (w *ScriptWidget) animateLaunch() {
	// 펄스 애니메이션 (작아졌다 커짐)
	
	// Simple scale animation: Fyne doesn't support direct scale transform on all objects easily without custom layout,
	// but we can animate opacity or simple sizing if layout permits.
	// For immediate visual feedback, let's flash the background and fade the icon slightly.
	
	fade := fyne.NewAnimation(200*time.Millisecond, func(v float32) {
		// v goes 0 -> 1
		// Opacity: 1 -> 0.5 -> 1
		if v < 0.5 {
			w.icon.Translucency = float64(v) // 0 -> 0.5 (fadout)
		} else {
			w.icon.Translucency = float64(1 - v) // 0.5 -> 0 (fadein)
		}
		w.icon.Refresh()
		
		// Background flash
		if v < 0.5 {
			w.background.FillColor = theme.SelectionColor()
		} else {
			w.background.FillColor = theme.HoverColor() // Return to hover state
		}
		w.background.Refresh()
	})
	fade.Start()
}

// 텍스트 래핑 헬퍼 함수 (개선됨: 긴 단어 자르기 포함)
func wrapSmart(text string, size float32, maxWidth float32) []string {
	if text == "" {
		return []string{}
	}
	
	style := fyne.TextStyle{}
	var lines []string
	var currentLine string

	// 1. 이미 줄바꿈이 있는 경우 처리? (일단 무시하고 one block으로 봄 or split)
	// 단순화를 위해 전체를 run array로 변환하여 처리 (Character Wrap)
	// 단어 단위 보존을 위해 먼저 Fields로 나누고, 너무 긴 단어는 쪼갭니다.
	
	words := strings.Fields(text)
	for _, word := range words {
		// 단어 자체가 maxWidth보다 긴 경우: 강제로 쪼개야 함
		if fyne.MeasureText(word, size, style).Width > maxWidth {
			// 현재 라인 비우고 시작
			if currentLine != "" {
				lines = append(lines, currentLine)
				currentLine = ""
			}
			
			// 글자 단위로 쪼개서 넣기
			runes := []rune(word)
			chunk := ""
			for _, r := range runes {
				testChunk := chunk + string(r)
				if fyne.MeasureText(testChunk, size, style).Width <= maxWidth {
					chunk = testChunk
				} else {
					lines = append(lines, chunk)
					chunk = string(r)
				}
			}
			if chunk != "" {
				currentLine = chunk // 마지막 조각을 현재 라인으로
			}
		} else {
			// 일반 단어 처리
			testLine := word
			if currentLine != "" {
				testLine = currentLine + " " + word
			}
			
			if fyne.MeasureText(testLine, size, style).Width <= maxWidth {
				currentLine = testLine
			} else {
				lines = append(lines, currentLine)
				currentLine = word
			}
		}
	}
	if currentLine != "" {
		lines = append(lines, currentLine)
	}

	// 최대 2줄 제한
	if len(lines) > 2 {
		lines = lines[:2]
		// lines[1] += "..." // 생략 표시 (선택사항)
	}

	return lines
}

func (w *ScriptWidget) TappedSecondary(e *fyne.PointEvent) {
	menu := fyne.NewMenu("",
		fyne.NewMenuItem("실행", func() { w.app.runScript(w.item) }),
		fyne.NewMenuItem("파일위치 열기", func() { w.app.openFileLocation(w.item) }),
		fyne.NewMenuItem("속성", func() { w.app.showPropertiesDialog(w.item) }),
	)
	
	widget.ShowPopUpMenuAtPosition(menu, w.app.Window.Canvas(), e.AbsolutePosition)
}