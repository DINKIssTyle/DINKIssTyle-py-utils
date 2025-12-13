package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/layout"
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
	InterpreterPath string
}

// --- 앱 설정 키 ---
const (
	KeyRegisteredFolders = "RegisteredFolders"
	KeyPythonPath        = "PythonPath"
	KeyIconSize          = "IconSize"
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

	// 검색
	SearchText  string
	SearchEntry *widget.Entry

	// 파일 감지
	Watcher *fsnotify.Watcher
}

func main() {
	myApp := app.NewWithID("com.pyquickbox.linux")
	myWindow := myApp.NewWindow("PyQuickBox (Linux)")

	launcher := &LauncherApp{
		App:      myApp,
		Window:   myWindow,
		Scripts:  make(map[string][]ScriptItem),
		IconSize: 80, // 기본값
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
	// 상단 툴바 (검색창 + 설정 버튼)
	l.SearchEntry = widget.NewEntry()
	l.SearchEntry.SetPlaceHolder("검색 (카테고리 또는 파일명)...")
	l.SearchEntry.OnChanged = func(s string) {
		l.SearchText = s
		l.updateGridUI() // 검색어 변경 시 그리드 갱신
	}

	settingsBtn := widget.NewButtonWithIcon("", theme.SettingsIcon(), func() {
		l.showSettingsDialog()
	})

	refreshBtn := widget.NewButtonWithIcon("", theme.ViewRefreshIcon(), func() {
		l.refreshScripts()
	})

	// 검색창 영역 레이아웃
	topBar := container.NewBorder(nil, nil, nil, container.NewHBox(refreshBtn, settingsBtn), l.SearchEntry)

	// 메인 컨텐츠 영역 (스크롤 가능)
	l.ContentBox = container.NewVBox() // 여기에 카테고리별 그리드가 들어감
	scrollArea := container.NewVScroll(l.ContentBox)

	// 하단 슬라이더 바 (아이콘 크기 조절)
	iconSlider := widget.NewSlider(60, 200)
	iconSlider.Value = float64(l.IconSize)
	iconSlider.OnChanged = func(f float64) {
		l.IconSize = float32(f)
		l.App.Preferences().SetFloat(KeyIconSize, float64(l.IconSize))
		l.updateGridUI()
	}

	bottomBar := container.NewBorder(nil, nil, widget.NewIcon(theme.ContentRemoveIcon()), widget.NewIcon(theme.ContentAddIcon()), iconSlider)

	// 전체 레이아웃 조립
	mainLayout := container.NewBorder(container.NewPadded(topBar), container.NewPadded(bottomBar), nil, nil, container.NewPadded(scrollArea))
	l.Window.SetContent(mainLayout)
}

// --- 그리드 UI 갱신 (핵심) ---
func (l *LauncherApp) updateGridUI() {
	l.ContentBox.Objects = nil // 기존 내용 초기화

	// 카테고리 순회
	for _, cat := range l.Categories {
		// 검색 필터링 로직
		matchedScripts := l.filterScripts(cat)
		if len(matchedScripts) == 0 {
			continue // 보여줄 스크립트가 없으면 섹션 숨김
		}

		// 섹션 헤더
		header := canvas.NewText(cat, theme.ForegroundColor())
		header.TextStyle.Bold = true
		header.TextSize = 16
		l.ContentBox.Add(container.NewVBox(header, widget.NewSeparator()))

		// 그리드 컨테이너 (GridWrap: 아이콘 크기에 따라 자동 줄바꿈)
		itemSize := fyne.NewSize(l.IconSize+20, l.IconSize+40)
		grid := container.NewGridWrap(itemSize)

		for _, script := range matchedScripts {
			// 클로저 변수 캡처
			s := script

			// 아이콘 생성
			var img *canvas.Image
			if s.IconPath != "" {
				img = canvas.NewImageFromFile(s.IconPath)
			} else {
				// 기본 아이콘
				img = canvas.NewImageFromResource(theme.FileIcon())
			}
			img.FillMode = canvas.ImageFillContain
			img.SetMinSize(fyne.NewSize(l.IconSize, l.IconSize))

			// 라벨 생성
			label := widget.NewLabel(s.Name)
			label.Alignment = fyne.TextAlignCenter
			label.Wrapping = fyne.TextWrapBreak

			// 클릭 가능한 카드 만들기
			btn := widget.NewButton("", func() {
				l.runScript(s)
			})
			btn.Importance = widget.LowImportance

			// 아이템 레이아웃
			itemContent := container.NewBorder(nil, label, nil, nil, img)
			clickableItem := container.NewMax(btn, itemContent)

			grid.Add(clickableItem)
		}
		l.ContentBox.Add(grid)
		l.ContentBox.Add(layout.NewSpacer()) // 섹션 간 간격
	}

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
				cat, interp := l.parseHeader(fullPath)

				item := ScriptItem{
					Name:            fileName,
					Path:            fullPath,
					Category:        cat,
					IconPath:        iconPath,
					InterpreterPath: interp,
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
	l.updateGridUI()

	// 감시 폴더 업데이트
	if l.Watcher != nil {
		for _, f := range l.RegisteredFolders {
			l.Watcher.Add(f)
		}
	}
}

// 파일 헤더 파싱 (#pqr)
func (l *LauncherApp) parseHeader(path string) (string, string) {
	file, err := os.Open(path)
	if err != nil {
		return "Uncategorized", ""
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	category := "Uncategorized"
	var interpreter string

	lineCount := 0
	for scanner.Scan() {
		if lineCount > 10 {
			break
		}
		line := strings.TrimSpace(scanner.Text())

		// 정규식
		// 1. #pqr cat "Category"
		if strings.HasPrefix(line, "#pqr cat") {
			re := regexp.MustCompile(`#pqr\s+cat\s+"([^"]+)"`)
			matches := re.FindStringSubmatch(line)
			if len(matches) > 1 {
				category = matches[1]
			}
		}

		// 2. #pqr linux ... (기존 호환)
		if strings.HasPrefix(line, "#pqr") && !strings.HasPrefix(line, "#pqr cat") {
			re := regexp.MustCompile(`#pqr\s+\w+.*"([^"]+)"\s*(.*)`)
			matches := re.FindStringSubmatch(line)
			if len(matches) > 1 {
				if category == "Uncategorized" {
					category = matches[1]
				}
				if len(matches) > 2 {
					interpreter = strings.TrimSpace(matches[2])
				}
			}
		}
		lineCount++
	}
	return category, interpreter
}

// --- 로직: 실행 ---
func (l *LauncherApp) runScript(s ScriptItem) {
	python := l.DefaultPythonPath
	if s.InterpreterPath != "" {
		python = s.InterpreterPath
	}
	if python == "" {
		python = "/usr/bin/python3" // 리눅스 기본값
	}

	fmt.Printf("Attempting to run: %s using %s\n", s.Name, python)

	// 백그라운드 실행
	cmd := exec.Command(python, s.Path)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	// 환경변수 설정
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

// --- 설정 및 데이터 관리 ---
func (l *LauncherApp) loadPreferences() {
	l.DefaultPythonPath = l.App.Preferences().StringWithFallback(KeyPythonPath, "/usr/bin/python3")
	l.IconSize = float32(l.App.Preferences().FloatWithFallback(KeyIconSize, 80))

	foldersJson := l.App.Preferences().String(KeyRegisteredFolders)
	if foldersJson != "" {
		json.Unmarshal([]byte(foldersJson), &l.RegisteredFolders)
	}
}

func (l *LauncherApp) savePreferences() {
	l.App.Preferences().SetString(KeyPythonPath, l.DefaultPythonPath)
	l.App.Preferences().SetFloat(KeyIconSize, float64(l.IconSize))

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
		widget.NewLabelWithStyle("등록된 폴더:", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		addFolderBtn,
		folderScroll,
	)

	d := dialog.NewCustom("환경 설정", "닫기", content, l.Window)
	d.Resize(fyne.NewSize(500, 500))

	d.SetOnClosed(func() {
		l.DefaultPythonPath = pythonEntry.Text
		l.savePreferences()
		l.refreshScripts()
	})

	d.Show()
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