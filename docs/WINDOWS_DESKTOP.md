# Story Factory Windows 桌面端

## 兼容性审查

项目 GUI 使用 NiceGUI。开发入口为 `factory studio` / `factory-gui`，桌面发布入口为
`factory.gui.desktop:main`。两者复用相同的 `FactoryService`、Workflow、Provider、Agent 与
Prompt，没有复制 Windows 专用业务逻辑。

审查结果：

- 支持目标：Windows 10/11 x64；不支持 Windows 7 和 32 位系统。
- 依赖由 `pyproject.toml` 管理；桌面发布使用 `desktop`、`models` extras。
- 源码未发现 `os.system`、`shell=True`、`fork`、`chmod` 或硬编码 `/Users/...`、
  `/home/...` 路径。
- Core 使用 `pathlib.Path` 和显式 UTF-8，中文用户名、目录及小说文件名可用。
- 模型层是 API Provider 架构，不要求 Ollama、本地 Qwen 或其他本地服务存在。
- SQLite、项目、配置、缓存和日志在发布版中写入用户目录，不写入安装目录。
- NiceGUI 桌面模式通过 pywebview 使用 Windows Edge WebView2；普通 Windows 10/11
  通常已有该组件。

## 用户目录

Windows 发布版首次启动会创建：

```text
%LOCALAPPDATA%\StoryFactory\
├── config\
│   ├── local.yaml
│   └── desktop.json
├── logs\
│   ├── storyfactory.log
│   ├── storyfactory.log.1
│   └── storyfactory.log.2
├── cache\
├── projects\
├── database\
└── runtime\
```

API Key 使用 Windows Credential Manager（`keyring`）保存，不写入上述 JSON/YAML、项目
文件或日志。本地大模型不打入 EXE；应用仅保存用户选定的模型目录。

## Windows 构建

构建必须在 Windows x64 上执行；PyInstaller 不能从 macOS 交叉编译 Windows EXE。
构建机需要 64 位 Python 3.11 或 3.12。PowerShell 在仓库根目录执行：

```powershell
.\scripts\build_windows.ps1
```

脚本会创建隔离构建环境、安装依赖、生成图标、运行测试、构建 onedir portable 包，
并在找到 Inno Setup 6 时继续生成安装包。

只生成 portable 包：

```powershell
.\scripts\build_windows.ps1 -SkipInstaller
```

输出：

```text
release\windows\portable\StoryFactory\StoryFactory.exe
release\windows\installer\StoryFactory-Setup-<version>.exe
```

若未安装 Inno Setup 6，可安装后执行：

```powershell
$version = .\.build-venv-windows\Scripts\python.exe -c "from factory.version import __version__; print(__version__)"
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" "/DMyAppVersion=$version" ".\installer\storyfactory.iss"
```

安装器默认安装到 Program Files，应用进程使用 `asInvoker`，不会请求管理员权限运行。
卸载只删除程序文件，默认保留 AppData 中的小说项目、配置和日志。

## Windows 验收清单

- [ ] Windows 10 x64 双击 `StoryFactory.exe` 可启动，且没有 CMD 窗口。
- [ ] Windows 11 x64 双击启动，标题栏、任务栏、Alt+Tab 和 EXE 图标一致。
- [ ] 在 100%、125%、150%、175%、200% DPI 下检查页面、弹窗和目录选择器。
- [ ] 使用中文 Windows 用户名和 `D:\小说项目\仙侠小说` 项目目录完成创建、保存、重启。
- [ ] 首次启动向导可跳过；未配置模型时仍能进入主界面。
- [ ] Provider 连接失败只显示友好错误，不导致应用退出。
- [ ] API Key 保存后不出现在 `desktop.json`、`local.yaml`、项目文件和日志中。
- [ ] 日志写入 `%LOCALAPPDATA%\StoryFactory\logs` 并发生轮转。
- [ ] SQLite/项目数据均在用户可写目录；Program Files 中无运行时写入。
- [ ] 第二次启动显示“已经在运行”，不创建第二个实例。
- [ ] 安装器创建开始菜单入口；勾选后创建桌面快捷方式。
- [ ] 正常卸载应用后，用户项目仍保留。
- [ ] Windows Defender/SmartScreen 扫描 portable 和安装包；正式发布前完成代码签名。

## 当前风险

- macOS 无法实机验证 Windows EXE、Inno Setup、任务栏图标与各 DPI 档；必须在 Windows
  10/11 x64 或 `windows-latest` runner 完成上表验收。
- Windows 原生模式依赖 Edge WebView2/.NET 运行组件；精简系统镜像可能需要额外安装。
- 当前正在运行的生成线程不能安全强制取消。用户应等待任务完成再关闭；后续可增加持久化
  任务管理器和关闭确认，不应通过杀线程实现。
- 未签名的内部测试包可能触发 SmartScreen。正式对外发布需购买代码签名证书，并为
  PyInstaller EXE 和 Inno Setup 安装器签名。
- `onedir` 是当前受支持发布形式；onefile 启动速度、杀毒误报和动态依赖尚未验收。

