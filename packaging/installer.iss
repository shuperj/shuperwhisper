; ShuperWhisper Windows Installer
; Inno Setup Script

#define MyAppName "ShuperWhisper"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "ShuperWhisper"
#define MyAppURL "https://github.com/shuperj/shuperwhisper"
#define MyAppExeName "ShuperWhisper.exe"

[Setup]
AppId={{B7E3F8A2-4D1C-4E5F-9A2B-1C3D5E7F9A2B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=ShuperWhisper-Setup-{#MyAppVersion}
SetupIconFile=ShuperWhisper.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
WizardImageFile=wizard_image.bmp
WizardSmallImageFile=wizard_small_image.bmp
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start ShuperWhisper with Windows"; GroupDescription: "Other options:"
Name: "gpu"; Description: "Set up GPU acceleration for live typing (downloads about 1.2 GB from NVIDIA)"; GroupDescription: "NVIDIA graphics card found:"; Check: HasNvidiaGpu

[Files]
Source: "..\dist\ShuperWhisper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userprograms}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup-gpu"; StatusMsg: "Setting up GPU acceleration..."; Tasks: gpu; Flags: waituntilterminated skipifsilent
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent shellexec

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[InstallDelete]
; A 1.x build's files must not linger next to the new ones.
Type: filesandordirs; Name: "{app}\_internal"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\cuda"
Type: filesandordirs; Name: "{app}\cuda.partial"

[Code]
var
  NvidiaChecked: Boolean;
  NvidiaName: String;

{ First NVIDIA adapter's name via WMI, or '' when there is none. }
function NvidiaGpuName(): String;
var
  Locator, Service, Items, Item: Variant;
  I: Integer;
  Name: String;
begin
  Result := '';
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Items := Service.ExecQuery('SELECT Name FROM Win32_VideoController');
    for I := 0 to Items.Count - 1 do
    begin
      Item := Items.ItemIndex(I);
      Name := Item.Name;  { a Variant: Uppercase() needs a String }
      if Pos('NVIDIA', Uppercase(Name)) > 0 then
      begin
        Result := Name;
        Exit;
      end;
    end;
  except
    Result := '';
  end;
end;

function HasNvidiaGpu(): Boolean;
begin
  if not NvidiaChecked then
  begin
    NvidiaName := NvidiaGpuName();
    NvidiaChecked := True;
  end;
  Result := NvidiaName <> '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    Exec('taskkill.exe', '/F /IM ShuperWhisper.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec('taskkill.exe', '/F /IM ShuperWhisper.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
