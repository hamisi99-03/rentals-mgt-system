; Inno Setup script for Rentals Manager (per-user install).
; Build with: iscc installer.iss after scripts\build_windows.ps1

#define MyAppName "Rentals Manager"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Rentals Manager"
#define MyAppExeName "RentalsManager.exe"
#define MyAppIcon "assets\icon-building.ico"

[Setup]
AppId={{7E4A8B0E-1F5A-4E4C-9A8D-2B4F8F5D1C21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=RentalsManager-Setup-{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\_internal\assets\icon-building.ico
; Business data lives in %LOCALAPPDATA%\RentalsManager and is intentionally not removed.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\RentalsManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\assets\icon-building.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\assets\icon-building.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
