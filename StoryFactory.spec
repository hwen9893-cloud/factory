"""PyInstaller onedir build for the native Story Factory desktop app."""

from pathlib import Path
import runpy

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve()
VERSION = runpy.run_path(str(ROOT / "factory" / "version.py"))["__version__"]
ICON = ROOT / "assets" / "icons" / "app.ico"
MANIFEST = ROOT / "packaging" / "windows" / "storyfactory.manifest"
VERSION_FILE = ROOT / "build" / "windows" / "version_info.txt"
VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)

version_parts = [int(part) for part in VERSION.split(".")]
version_tuple = tuple((version_parts + [0, 0, 0, 0])[:4])
VERSION_FILE.write_text(
    "VSVersionInfo(ffi=FixedFileInfo(filevers=%r, prodvers=%r, mask=0x3f, flags=0x0, "
    "OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), kids=[StringFileInfo(["
    "StringTable('040904B0', [StringStruct('CompanyName', 'Story Factory'), "
    "StringStruct('FileDescription', 'AI Novel Creation Workstation'), "
    "StringStruct('FileVersion', '%s'), StringStruct('InternalName', 'StoryFactory'), "
    "StringStruct('OriginalFilename', 'StoryFactory.exe'), StringStruct('ProductName', 'Story Factory'), "
    "StringStruct('ProductVersion', '%s')])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])"
    % (version_tuple, version_tuple, VERSION, VERSION),
    encoding="utf-8",
)

nicegui_datas, nicegui_binaries, nicegui_hidden = collect_all("nicegui")
webview_datas, webview_binaries, webview_hidden = collect_all("webview")
hiddenimports = nicegui_hidden + webview_hidden + [
    "tkinter",
    "tkinter.filedialog",
    "keyring.backends.Windows",
]
for package in ("openai", "anthropic", "google.genai"):
    hiddenimports += collect_submodules(package)

datas = nicegui_datas + webview_datas + [
    (str(ROOT / "config" / "default.yaml"), "config"),
    (str(ROOT / "factory" / "prompts"), "factory/prompts"),
    (str(ICON), "assets/icons"),
]
try:
    datas += copy_metadata("novel-factory")
except Exception:
    pass

a = Analysis(
    [str(ROOT / "factory" / "gui" / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=nicegui_binaries + webview_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StoryFactory",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ICON),
    version=str(VERSION_FILE),
    manifest=str(MANIFEST),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="StoryFactory",
)
