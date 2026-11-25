; Inno Setup script for Claude Buddy. Built by packaging/build.ps1 (passes /DAppVersion=x.y.z).
; Per-user install: no administrator rights needed.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Claude Buddy"
#define AppExe "ClaudeBuddy.exe"

[Setup]
; Fixed AppId: upgrades replace the previous version instead of installing side by side
AppId={{B2D01D80-776A-4578-8018-80FCF44F5E10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ClaudeBuddy-Setup-{#AppVersion}
SetupIconFile=..\build\claude-buddy.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "autostart"; Description: "Iniciar Claude Buddy al arrancar Windows"; GroupDescription: "Opciones:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Remove files of a previous version before copying the new ones
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\ClaudeBuddy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ClaudeBuddy"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; The app lives in the tray: close it so its files can be removed
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#AppExe}"; Flags: runhidden; RunOnceId: "StopClaudeBuddy"

[Code]
function ClaudeCodeFound(): Boolean;
begin
  Result := FileExists(ExpandConstant('{%USERPROFILE}\.local\bin\claude.exe'))
    or FileExists(ExpandConstant('{%USERPROFILE}\.claude\local\claude.exe'))
    or (FileSearch('claude.exe', GetEnv('PATH')) <> '')
    or (FileSearch('claude.cmd', GetEnv('PATH')) <> '');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and not ClaudeCodeFound() and not WizardSilent() then
    MsgBox('No se ha encontrado Claude Code en este equipo.'#13#10#13#10 +
           'Claude Buddy puede listar tus sesiones, pero para chatear necesita Claude Code instalado ' +
           'y con la sesión iniciada (comando "claude").', mbInformation, MB_OK);
end;
