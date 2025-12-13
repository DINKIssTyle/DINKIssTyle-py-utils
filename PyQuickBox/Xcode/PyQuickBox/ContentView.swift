import SwiftUI

struct ContentView: View {
    @StateObject var viewModel = LauncherViewModel()
    @State private var showSettings = false
    
    // [추가] 검색창 활성화 상태 관리
    @State private var isSearchActive = false
    
    // [추가] 검색창이 열리면 자동으로 포커스(커서)를 주기 위한 변수
    @FocusState private var isSearchFocused: Bool
    
    var body: some View {
        VStack(spacing: 0) {
            // 1. 상단 툴바 영역 (검색창 포함)
            HStack {
                Spacer() // 왼쪽 여백을 채워서 아이콘을 우측으로 보냄 (파인더 스타일)
                
                if isSearchActive {
                    // [활성 상태] 입력창 + 닫기 버튼
                    HStack {
                        Image(systemName: "magnifyingglass")
                            .foregroundColor(.gray)
                        
                        TextField("검색...", text: $viewModel.searchText)
                            .textFieldStyle(PlainTextFieldStyle())
                            .focused($isSearchFocused) // 포커스 연결
                        
                        // 닫기 버튼
                        Button(action: {
                            withAnimation(.spring()) {
                                viewModel.searchText = "" // 검색어 초기화
                                isSearchActive = false    // 닫기
                                isSearchFocused = false   // 포커스 해제
                            }
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.gray)
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                    .padding(8)
                    .frame(width: 250) // 입력창 너비 고정
                    .background(Color(NSColor.controlBackgroundColor))
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                    )
                    .transition(.move(edge: .trailing).combined(with: .opacity)) // 우측에서 스르륵 나오는 효과
                } else {
                    // [비활성 상태] 돋보기 버튼만 표시
                    Button(action: {
                        withAnimation(.spring()) {
                            isSearchActive = true
                            isSearchFocused = true // 열리자마자 커서 깜빡임
                        }
                    }) {
                        Image(systemName: "magnifyingglass")
                            .font(.title2)
                            .foregroundColor(.primary)
                            .padding(8)
                            .contentShape(Rectangle()) // 클릭 영역 확보
                    }
                    .buttonStyle(PlainButtonStyle())
                    .transition(.opacity)
                }
            }
            .padding(.horizontal, 15)
            .padding(.vertical, 10)
            .frame(height: 50) // 툴바 높이 고정
            
            Divider()
            
            // 2. 메인 스크롤 영역
            ScrollView {
                LazyVGrid(
                    columns: [
                        GridItem(.adaptive(minimum: viewModel.iconSize + 10), spacing: 20, alignment: .top)
                    ],
                    spacing: 30
                ) {
                    ForEach(viewModel.visibleCategories, id: \.self) { category in
                        Section(header: HeaderView(title: category)) {
                            ForEach(viewModel.visibleScripts(in: category)) { script in
                                ScriptCell(script: script, size: viewModel.iconSize, fontSize: viewModel.labelFontSize)
                                    .onTapGesture {
                                        viewModel.runScript(script)
                                    }
                            }
                        }
                    }
                }
                .padding()
            }
            
            Divider()
            
            // 3. 하단 컨트롤 바
            HStack {
                Button(action: { showSettings.toggle() }) {
                    Image(systemName: "gearshape")
                        .font(.title2)
                }
                .help("환경 설정")
                
                Spacer()
                
                Image(systemName: "photo")
                Slider(value: $viewModel.iconSize, in: 60...200)
                    .frame(width: 200)
                Image(systemName: "photo.fill")
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))
        }
        .frame(minWidth: 600, minHeight: 500)
        .sheet(isPresented: $showSettings) {
            SettingsView(viewModel: viewModel)
        }
        .onAppear {
            viewModel.refreshScripts()
        }
    }
}

// 섹션 헤더 뷰
struct HeaderView: View {
    let title: String
    var body: some View {
        VStack(alignment: .leading) {
            Text(title)
                .font(.title2)
                .fontWeight(.bold)
                .foregroundColor(.secondary)
            Divider()
        }
        .padding(.top, 20)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// 개별 아이콘 셀 뷰
struct ScriptCell: View {
    let script: ScriptItem
    let size: CGFloat
    let fontSize: Double
    
    var body: some View {
        VStack(spacing: 8) {
            if let img = script.image {
                Image(nsImage: img)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: size, height: size)
                    .shadow(radius: 2)
            }
            
            Text(script.name)
                .font(.system(size: CGFloat(fontSize)))
                .fontWeight(.medium)
                .foregroundColor(.primary)
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .truncationMode(.tail)
                .frame(width: size + 10)
        }
        .padding(5)
        .background(Color.clear)
        .contentShape(Rectangle())
    }
}
