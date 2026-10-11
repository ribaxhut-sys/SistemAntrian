#define MyAppName "Sistem Antrian CRO"
#define MyAppVersion "1.0.3"
#define MyAppPublisher "Sistem Antrian CRO"
#define MyAppExeName "AntrianCRO.exe"
#define SourceDir GetEnv("ANTRIAN_SOURCE_DIR")
#define OutputDir GetEnv("ANTRIAN_OUTPUT_DIR")

[Setup]
AppId={{C1D360FA-F11B-49A7-8B0E-218CC9A1B8E9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\AntrianCRO
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir={#OutputDir}
OutputBaseFilename=AntrianCRO-Setup-1.0.3
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Buat ikon di Desktop"; GroupDescription: "Ikon tambahan:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; DLL PySide6/Qt lama dapat tertinggal ketika versi aplikasi diperbarui dan
; membuat QtWidgets gagal dimuat bersama DLL dari versi lain.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\Sistem Antrian CRO"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Sistem Antrian CRO"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Jalankan Sistem Antrian CRO"; Flags: nowait postinstall skipifsilent
