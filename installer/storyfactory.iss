#ifndef MyAppVersion
  #error MyAppVersion must be supplied by scripts\build_windows.ps1
#endif

#define MyAppName "Story Factory"
#define MyAppExeName "StoryFactory.exe"
#define MyAppPublisher "Story Factory"

[Setup]
AppId={{6F069450-6905-4D18-92EB-EECFEEBFDB93}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=AI Novel Creation Workstation
DefaultDirName={autopf}\StoryFactory
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release\windows\installer
OutputBaseFilename=StoryFactory-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icons\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Uninstallable=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Files]
Source: "..\release\windows\portable\StoryFactory\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Deliberately no uninstall-delete entries under AppData. User projects,
; configuration and logs survive uninstall and can be removed manually.
