#define MyAppName "Sistem Antrian CRO"
#define MyAppVersion "1.0.6"
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
OutputBaseFilename=AntrianCRO-Setup-1.0.6
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=assets\ikon\antrian.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Aplikasi lama ditutup sendiri di PrepareToInstall (lihat [Code]). Restart
; Manager hanya menampilkan dialog teknis "aplikasi berikut harus ditutup"
; yang membingungkan petugas, dan tidak melihat proses API di latar belakang.
CloseApplications=no
; Pembaruan memakai folder dan pilihan ikon dari pemasangan sebelumnya.
DisableDirPage=auto
UsePreviousAppDir=yes
UsePreviousTasks=yes

[Messages]
; Inno Setup tidak menyertakan bahasa Indonesia; yang dilihat petugas saja.
ButtonBack=< &Kembali
ButtonNext=&Lanjut >
ButtonInstall=&Pasang
ButtonCancel=Batal
ButtonFinish=&Selesai
ButtonBrowse=&Telusuri...
ExitSetupTitle=Batalkan pemasangan
ExitSetupMessage=Pemasangan belum selesai. Batalkan sekarang?
WizardSelectTasks=Pilihan tambahan
SelectTasksDesc=Pilih yang ingin dibuat.
WizardReady=Siap dipasang
ReadyLabel1=Sistem Antrian CRO siap dipasang.
ReadyLabel2a=Tekan Pasang untuk mulai.
WizardInstalling=Sedang memasang
InstallingLabel=Mohon tunggu, Sistem Antrian CRO sedang dipasang.
FinishedHeadingLabel=Selesai
FinishedLabelNoIcons=Sistem Antrian CRO sudah terpasang.
FinishedLabel=Sistem Antrian CRO sudah terpasang.
ClickFinish=Tekan Selesai untuk menutup jendela ini.
RunEntryExec=Jalankan Sistem Antrian CRO

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

[Code]
const
  KunciUninstall = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{C1D360FA-F11B-49A7-8B0E-218CC9A1B8E9}_is1';

var
  VersiTerpasang: String;

{ Bagian angka ke-Indeks (0, 1, 2, ...) dari "1.0.6"; 0 bila tidak ada. }
function BagianVersi(Versi: String; Indeks: Integer): Integer;
var
  Posisi: Integer;
begin
  while Indeks > 0 do
  begin
    Posisi := Pos('.', Versi);
    if Posisi = 0 then
    begin
      Result := 0;
      Exit;
    end;
    Delete(Versi, 1, Posisi);
    Indeks := Indeks - 1;
  end;
  Posisi := Pos('.', Versi);
  if Posisi > 0 then
    Versi := Copy(Versi, 1, Posisi - 1);
  Result := StrToIntDef(Versi, 0);
end;

{ Negatif bila A lebih lama dari B, nol bila sama, positif bila lebih baru. }
function BandingkanVersi(A, B: String): Integer;
var
  I: Integer;
begin
  Result := 0;
  for I := 0 to 3 do
  begin
    Result := BagianVersi(A, I) - BagianVersi(B, I);
    if Result <> 0 then
      Exit;
  end;
end;

function SedangMemperbarui: Boolean;
begin
  Result := VersiTerpasang <> '';
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not RegQueryStringValue(HKA, KunciUninstall, 'DisplayVersion', VersiTerpasang) then
    VersiTerpasang := '';

  { Installer lama yang tidak sengaja dijalankan tidak boleh menurunkan versi. }
  if SedangMemperbarui and (BandingkanVersi(VersiTerpasang, '{#MyAppVersion}') > 0) then
  begin
    SuppressibleMsgBox(
      'Versi yang terpasang (' + VersiTerpasang + ') sudah lebih baru daripada installer ini ({#MyAppVersion}).' + #13#10#13#10 +
      'Tidak ada yang perlu dipasang. Jendela ini akan ditutup.',
      mbInformation, MB_OK, IDOK);
    Result := False;
  end;
end;

{ Pembaruan cukup dua layar: pesan "Perbarui", lalu Selesai. }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := SedangMemperbarui and ((PageID = wpSelectDir) or (PageID = wpSelectTasks));
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpReady) and SedangMemperbarui then
  begin
    WizardForm.PageNameLabel.Caption := 'Pembaruan Sistem Antrian CRO';
    WizardForm.PageDescriptionLabel.Caption := 'Versi ' + VersiTerpasang + ' akan diganti dengan versi {#MyAppVersion}.';
    WizardForm.ReadyLabel.Caption :=
      'Sistem Antrian CRO akan diperbarui dari versi ' + VersiTerpasang + ' ke versi {#MyAppVersion}.' + #13#10#13#10 +
      'Data antrian dan pengaturan TIDAK berubah.' + #13#10#13#10 +
      'Aplikasi yang sedang terbuka akan ditutup otomatis, lalu dibuka kembali setelah selesai. ' +
      'Pastikan tidak sedang melayani pengunjung.' + #13#10#13#10 +
      'Di komputer server, Windows akan meminta izin: tekan Ya.' + #13#10#13#10 +
      'Tekan Perbarui untuk mulai.';
    WizardForm.ReadyMemo.Visible := False;
    WizardForm.NextButton.Caption := '&Perbarui';
  end;
  if (CurPageID = wpFinished) and SedangMemperbarui then
    WizardForm.FinishedLabel.Caption :=
      'Sistem Antrian CRO sudah diperbarui ke versi {#MyAppVersion}.' + #13#10#13#10 +
      'Tekan Selesai; aplikasi akan terbuka kembali.';
end;

const
  NamaTugasApi = 'AntrianCRO API Anjungan';

{ Penanda antara installer dan skrip penjeda API yang berjalan sebagai
  Administrator. Di folder temp pengguna, bukan folder tmp installer: folder tmp installer sudah dihapus
  saat DeinitializeSetup, padahal penanda "selesai" juga ditulis di sana. }
function BerkasPenanda(Akhiran: String): String;
begin
  Result := AddBackslash(GetTempDir) + 'AntrianCRO-pembaruan.' + Akhiran;
end;

function JalankanTersembunyi(Berkas, Argumen: String): Integer;
begin
  if not Exec(Berkas, Argumen, '', SW_HIDE, ewWaitUntilTerminated, Result) then
    Result := -1;
end;

{ API anjungan di komputer server berjalan sebagai tugas Task Scheduler akun
  SYSTEM (lihat app/services/kiosk_server.py). Pengguna biasa boleh
  membacanya, tetapi tidak dapat mematikan prosesnya. }
function TugasApiAda: Boolean;
begin
  Result := JalankanTersembunyi(ExpandConstant('{sys}\schtasks.exe'),
    '/Query /TN "' + NamaTugasApi + '"') = 0;
end;

function AplikasiMasihBerjalan: Boolean;
begin
  Result := JalankanTersembunyi(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -Command "if (Get-Process -Name AntrianCRO -ErrorAction SilentlyContinue) { exit 1 }"') = 1;
end;

{ Skrip yang dijalankan sekali sebagai Administrator: matikan tugas API
  (supaya pemicu penjaga 5 menit tidak menyalakannya di tengah pemasangan),
  hentikan semua AntrianCRO.exe, beri tanda, tunggu installer selesai, lalu
  nyalakan tugasnya lagi. Satu dialog UAC untuk seluruh pembaruan. }
function SkripJedaApi: String;
begin
  Result :=
    'param([string]$Penanda)' + #13#10 +
    '$nama = ''' + NamaTugasApi + '''' + #13#10 +
    '$tugas = Get-ScheduledTask -TaskName $nama -ErrorAction SilentlyContinue' + #13#10 +
    '$aktif = $tugas -and $tugas.State -ne ''Disabled''' + #13#10 +
    'if ($aktif) { Disable-ScheduledTask -TaskName $nama | Out-Null }' + #13#10 +
    'if ($tugas) { Stop-ScheduledTask -TaskName $nama -ErrorAction SilentlyContinue }' + #13#10 +
    'Get-Process -Name AntrianCRO -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue' + #13#10 +
    'Start-Sleep -Seconds 1' + #13#10 +
    'New-Item -ItemType File -Path ($Penanda + ''.berhenti'') -Force | Out-Null' + #13#10 +
    '$batas = (Get-Date).AddMinutes(20)' + #13#10 +
    'while (-not (Test-Path ($Penanda + ''.selesai'')) -and (Get-Date) -lt $batas) { Start-Sleep -Seconds 1 }' + #13#10 +
    'if ($aktif) { Enable-ScheduledTask -TaskName $nama | Out-Null; Start-ScheduledTask -TaskName $nama }' + #13#10;
end;

{ Nol bila tidak perlu, satu bila API sudah dijeda, negatif bila gagal. }
function JedaApiSebagaiAdministrator: Integer;
var
  Skrip: String;
  Kode, I: Integer;
begin
  Result := 0;
  if not (TugasApiAda or AplikasiMasihBerjalan) then
    Exit;

  Skrip := BerkasPenanda('ps1');
  DeleteFile(BerkasPenanda('berhenti'));
  DeleteFile(BerkasPenanda('selesai'));
  if not SaveStringToFile(Skrip, SkripJedaApi, False) then
  begin
    Result := -1;
    Exit;
  end;
  if not ShellExec('runas', ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + Skrip +
    '" -Penanda "' + AddBackslash(GetTempDir) + 'AntrianCRO-pembaruan"',
    '', SW_HIDE, ewNoWait, Kode) then
  begin
    Result := -1;
    Exit;
  end;
  for I := 1 to 60 do
  begin
    if FileExists(BerkasPenanda('berhenti')) then
    begin
      Result := 1;
      Exit;
    end;
    Sleep(500);
  end;
  Result := -1;
end;

procedure TandaiSelesai;
begin
  SaveStringToFile(BerkasPenanda('selesai'), '', False);
end;

{ Tutup semua AntrianCRO.exe, termasuk API anjungan di latar belakang, supaya
  berkas lama dapat ditimpa tanpa dialog. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  JalankanTersembunyi(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM {#MyAppExeName}');
  { Windows perlu sesaat untuk melepas berkas yang tadi dipegang prosesnya. }
  Sleep(1500);
  if JedaApiSebagaiAdministrator < 0 then
    Result :=
      'API anjungan di komputer ini belum dapat dihentikan sementara.' + #13#10#13#10 +
      'Saat Windows menanyakan izin, tekan "Ya". Tutup jendela ini, lalu jalankan pembaruan sekali lagi.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    TandaiSelesai;
end;

{ Juga bila pemasangan dibatalkan atau gagal: API tidak boleh tertinggal mati. }
procedure DeinitializeSetup;
begin
  if FileExists(BerkasPenanda('berhenti')) and not FileExists(BerkasPenanda('selesai')) then
    TandaiSelesai;
end;
