; Installateur Windows de Rétro Station — par Fabrice M.
#define AppName "Rétro Station"
#define AppVersion GetEnv("RS_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8F3C2A51-7D4E-4B8A-9C61-2E5F0A7B3D19}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Fabrice M.
AppCopyright=Fabrice M.
DefaultDirName={autopf}\Retro Station
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\installers
OutputBaseFilename=RetroStation-Setup-{#AppVersion}-Windows
SetupIconFile=..\..\assets\icon.ico
UninstallDisplayIcon={app}\RetroStation.exe
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoCompany=Fabrice M.
VersionInfoProductName={#AppName}
VersionInfoVersion={#AppVersion}

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\RetroStation\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\RetroStation.exe"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\RetroStation.exe"; Tasks: desktopicon

[Run]
; Composants Microsoft nécessaires au moteur Wii / GameCube (ignoré s'ils sont déjà là)
Filename: "{cmd}"; Parameters: "/c winget install -e --id Microsoft.VCRedist.2015+.x64 --silent --accept-package-agreements --accept-source-agreements"; StatusMsg: "Installation des composants Microsoft…"; Flags: runhidden waituntilterminated
Filename: "{app}\RetroStation.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
