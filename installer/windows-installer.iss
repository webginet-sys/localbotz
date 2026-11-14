; LocalBotz — professional Windows installer (Inno Setup 6).
;
; Built by GitHub Actions (.github/workflows/build-windows-installer.yml)
; into LocalBotz-Setup.exe. Like an Autodesk / Adobe / Microsoft installer:
;   Welcome -> Licence agreement -> Install folder -> Data folder
;   (C: drive or D: drive, so the C: drive stays light) -> Install
;   -> Finish (launch LocalBotz) -> Start Menu + Desktop shortcuts
;   -> Uninstaller in Add/Remove Programs.
;
; Per-user install, no admin rights needed: the app goes to
; %LOCALAPPDATA%\Programs\LocalBotz. The installer only copies files and
; shortcuts. The first launch runs start.bat, which does the full setup
; in that one step — Python, LM Studio + Qwen3.5, all Python libraries,
; Playwright + Chromium, desktop control — and then starts the app.
;
; Code signing: the workflow signs LocalBotz-Setup.exe when the
; WEBGINET ENTERPRISE PRIVATE LIMITED code-signing certificate is
; configured as GitHub secrets (WINDOWS_CERT_PFX + WINDOWS_CERT_PASSWORD).
; Until then the exe is unsigned: Windows SmartScreen shows "Windows
; protected your PC" with a "Run anyway" link — still far better than
; Smart App Control hard-blocking the .bat files, which have no
; run-anyway option at all.

#define MyAppName "LocalBotz"
#define MyAppVersion "0.3.0"
#define MyAppPublisher "WEBGINET ENTERPRISE PRIVATE LIMITED"
#define MyAppURL "https://localbotz.io"

[Setup]
AppId={{3F2A1B4C-7E8D-4A5B-9C0D-1E2F3A4B5C6D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL=https://github.com/webginet-sys/localbotz/releases
AppCopyright=Copyright (c) 2026 {#MyAppPublisher}
DefaultDirName={autopf}\LocalBotz
DefaultGroupName=LocalBotz
LicenseFile=..\LICENSE
SetupIconFile=localbotz.ico
UninstallDisplayIcon={app}\start.bat
OutputDir=..\installer-output
OutputBaseFilename=LocalBotz-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
ShowLanguageDialog=no
LanguageDetectionMethod=none

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Staged by the workflow into staging\ at the repo root (everything in
; the repo except .git, .github, .venv, data, __pycache__).
Source: "..\staging\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LocalBotz"; Filename: "{app}\start.bat"; WorkingDir: "{app}"; IconFilename: "{app}\installer\localbotz.ico"
Name: "{group}\Uninstall LocalBotz"; Filename: "{uninstallexe}"
Name: "{autodesktop}\LocalBotz"; Filename: "{app}\start.bat"; WorkingDir: "{app}"; IconFilename: "{app}\installer\localbotz.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\start.bat"; Description: "Launch LocalBotz now (first launch sets up Python, LM Studio and the model)"; Flags: postinstall nowait skipifsilent

[Code]
var
  DataDirPage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  { Data folder page, right after the install-folder page. This is the
    same choice start.bat asks about: C: drive (app folder) or D: drive
    (D:\LocalBotzData), so the C: drive stays light. }
  DataDirPage := CreateInputOptionPage(wpSelectDir,
    'Where should LocalBotz keep its data?',
    'Your bots, memory, offices, workrooms and documents live in one folder.',
    'The app itself stays in the install folder — only the data moves. ' +
    'Pick D: to keep the C: drive light. You can change it later in ' +
    'Settings -> General -> Data folder.',
    True, False);
  DataDirPage.Add('In the LocalBotz folder (C: drive)');
  DataDirPage.Add('On the D: drive — D:\LocalBotzData');
  DataDirPage.Add('Decide later (in the app, first-run wizard)');
  DataDirPage.Values[0] := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvFile: String;
begin
  if CurStep = ssPostInstall then
  begin
    { D: drive chosen and the drive exists: save the choice so the app
      uses it from the very first launch. No D: drive -> fall back to
      the app folder silently; the app asks again in its first-run wizard. }
    if DataDirPage.Values[1] and DirExists('D:\') then
    begin
      EnvFile := ExpandConstant('{app}\.env');
      SaveStringToFile(EnvFile, 'LOCALBOTZ_DATA_DIR=D:\LocalBotzData' + #13#10, True);
    end;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  { Keep the user's data by default: uninstall removes the app, not
    their memory. The data folder (app folder or D:\LocalBotzData) stays
    on disk unless they delete it by hand. }
  Result := True;
end;
