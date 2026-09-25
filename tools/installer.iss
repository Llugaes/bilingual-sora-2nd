#ifndef AppVersion
  #error AppVersion must be supplied by the build script
#endif

[Setup]
AppId={{F5F851F5-DB86-45CA-A522-2C5BD87DBF19}
AppName=Bilingual Sora 2nd
AppVersion={#AppVersion}
AppPublisher=Llugaes
AppPublisherURL=https://github.com/Llugaes/bilingual-sora-2nd
AppSupportURL=https://github.com/Llugaes/bilingual-sora-2nd/issues
AppUpdatesURL=https://github.com/Llugaes/bilingual-sora-2nd/releases/latest
DefaultDirName={localappdata}\Programs\Bilingual Sora 2nd
DefaultGroupName=Bilingual Sora 2nd
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=auto
DisableDirPage=no
WizardStyle=modern
SetupIconFile={#PayloadDir}\assets\sora-bilingual.ico
UninstallDisplayIcon={app}\BilingualSora2nd.exe
LicenseFile={#PayloadDir}\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename=bilingual-sora-2nd-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
CloseApplications=no
RestartApplications=no
Uninstallable=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "installer-language\ChineseSimplified.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[CustomMessages]
english.ExitTool=Please exit Bilingual Sora 2nd from its tray menu and end the game connection before continuing. Setup will not close the game.
chinesesimplified.ExitTool=请先从托盘退出双语工具，并结束游戏连接，再继续。安装程序不会强行关闭游戏。
japanese.ExitTool=トレイからツールを終了し、ゲームとの接続を終了してから続行してください。ゲームを強制終了することはありません。
english.RecoverFirst=An interrupted update needs recovery. Run the existing BilingualSora2nd.exe once, exit it, then retry; or select a new folder.
chinesesimplified.RecoverFirst=上次更新尚未恢复。请运行原目录的 BilingualSora2nd.exe 完成恢复，退出后重试；也可以选择新的安装目录。
japanese.RecoverFirst=中断した更新を復旧する必要があります。既存の BilingualSora2nd.exe を一度実行して終了後に再試行するか、新しいフォルダーを選択してください。
english.NewerVersion=A newer version is already installed here. Use the latest installer or select a new folder.
chinesesimplified.NewerVersion=此目录已安装更新的版本。请下载最新安装程序，或选择新的目录。
japanese.NewerVersion=このフォルダーには新しいバージョンがインストールされています。最新のインストーラーか新しいフォルダーを使用してください。

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Bilingual Sora 2nd"; Filename: "{app}\BilingualSora2nd.exe"
Name: "{autodesktop}\Bilingual Sora 2nd"; Filename: "{app}\BilingualSora2nd.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BilingualSora2nd.exe"; Description: "{cm:LaunchProgram,Bilingual Sora 2nd}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only the application's reserved runtime directory; never generated user data.
Type: filesandordirs; Name: "{app}\runtime"

[Code]
function CreateFileW(FileName: String; DesiredAccess, ShareMode: Cardinal;
  Security: Integer; CreationDisposition, Flags: Cardinal; Template: Integer): THandle;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function InUse(FileName: String; Access, Share: Cardinal): Boolean;
var Handle: THandle;
begin
  Result := False;
  if not FileExists(FileName) then exit;
  Handle := CreateFileW(FileName, Access, Share, 0, 3, 0, 0);
  Result := Handle = THandle(-1);
  if not Result then CloseHandle(Handle);
end;

function ToolRunning: Boolean;
var Runtime: AnsiString;
begin
  Result := InUse(ExpandConstant('{app}\generated\native-backend.lock'), $80000000, 0);
  if LoadStringFromFile(ExpandConstant('{app}\runtime\current.txt'), Runtime) then begin
    Result := Result or InUse(ExpandConstant('{app}\runtime\') + Trim(String(Runtime)) + '\pythonw.exe', $40000000, 7);
    Result := Result or InUse(ExpandConstant('{app}\runtime\') + Trim(String(Runtime)) + '\python.exe', $40000000, 7);
  end;
end;

function NewerInstalled: Boolean;
var Data: AnsiString; Text, Version: String; Position: Integer;
  Existing, Incoming: Int64;
begin
  Result := False;
  if not LoadStringFromFile(ExpandConstant('{app}\distribution.json'), Data) then exit;
  Text := String(Data);
  Position := Pos('"version"', Text);
  if Position = 0 then exit;
  Text := Copy(Text, Position + 9, Length(Text));
  Position := Pos('"', Text);
  if Position = 0 then exit;
  Text := Copy(Text, Position + 1, Length(Text));
  Position := Pos('"', Text);
  if Position = 0 then exit;
  Version := Copy(Text, 1, Position - 1);
  if StrToVersion(Version, Existing) and StrToVersion('{#AppVersion}', Incoming) then
    Result := ComparePackedVersion(Existing, Incoming) > 0;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if ToolRunning then
    Result := CustomMessage('ExitTool');
  if FileExists(ExpandConstant('{app}\generated\updates\transaction.json')) then
    Result := CustomMessage('RecoverFirst');
  if NewerInstalled then Result := CustomMessage('NewerVersion');
end;

function InitializeUninstall: Boolean;
begin
  Result := not ToolRunning;
  if not Result then
    MsgBox(CustomMessage('ExitTool'), mbError, MB_OK);
end;
