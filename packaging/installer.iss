; Inno Setup script for the SAIMS Windows installer. build.bat runs it if Inno Setup 6 is installed.
#define AppName "SAIMS"
#define AppVersion "0.1.0"

[Setup]
AppId={{9B6F3D41-2C7E-4E2A-8B1D-5A7C3E9F1D22}
AppName={#AppName}
AppVerName=SAIMS {#AppVersion} - School Asset & Inventory Management System
AppVersion={#AppVersion}
DefaultDirName={autopf}\SAIMS
DefaultGroupName=SAIMS
UninstallDisplayIcon={app}\SAIMS.exe
OutputDir=..\dist
OutputBaseFilename=SAIMS-{#AppVersion}-Setup
SetupIconFile=saims.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\SAIMS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SAIMS"; Filename: "{app}\SAIMS.exe"
Name: "{group}\Uninstall SAIMS"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SAIMS"; Filename: "{app}\SAIMS.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SAIMS.exe"; Description: "Launch SAIMS"; Flags: nowait postinstall skipifsilent
