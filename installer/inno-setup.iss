; Inno Setup script — alternative installer for EnterpriseCore AI Suite
; Use this when you need fine-grained control over installation (Start Menu shortcuts,
; firewall rules, file associations) beyond what electron-builder provides.

#define MyAppName "EnterpriseCore AI Suite"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "EnterpriseCore"
#define MyAppExeName "EnterpriseCore AI Suite.exe"

[Setup]
AppId={{A7E50C84-1F4A-4A1E-9D9B-EC50C0001001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\EnterpriseCore
DefaultGroupName=EnterpriseCore
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=EnterpriseCore-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "firewall"; Description: "Allow inbound connections on TCP/8765 (local API)"; GroupDescription: "Networking:"; Flags: unchecked

[Files]
; Built artifacts produced by `npm run build:exe`
Source: "..\electron\dist\win-unpacked\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""EnterpriseCore Backend"" dir=in action=allow protocol=TCP localport=8765"; Flags: runhidden; Tasks: firewall
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""EnterpriseCore Backend"""; Flags: runhidden
