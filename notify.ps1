param(
    [Parameter(Mandatory = $true)]
    [string]$Message
)

# Show a Windows toast notification. Uses the registered PowerShell AUMID as the
# AppID so the toast reliably appears without registering a custom shortcut.
# Clicking the toast activates the claude-code-focus:// protocol, which brings
# the terminal hosting Claude Code back to the foreground.
$ErrorActionPreference = 'Stop'

$protocol = 'claude-code-focus'
$focusScript = Join-Path $PSScriptRoot 'focus-terminal.ps1'
$hwndFile = Join-Path $env:TEMP 'claude_terminal_hwnd.txt'

# Walk up the process tree from this script to the first ancestor that owns a
# visible window (Windows Terminal, conhost, VS Code, etc.) and remember it so
# the protocol handler knows what to focus.
function Get-TerminalHwnd {
    $procId = $PID
    for ($i = 0; $i -lt 16; $i++) {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        if (-not $p -or -not $p.ParentProcessId) { break }
        $procId = [int]$p.ParentProcessId
        try {
            $proc = Get-Process -Id $procId -ErrorAction Stop
            if ($proc.MainWindowHandle -ne [IntPtr]::Zero) {
                return [int64]$proc.MainWindowHandle
            }
        }
        catch { break }
    }
    return 0
}

try {
    $hwnd = Get-TerminalHwnd
    if ($hwnd -ne 0) {
        Set-Content -Path $hwndFile -Value $hwnd -NoNewline -Encoding ASCII
    }
}
catch { }

# Register the protocol handler under HKCU (idempotent, no admin needed).
try {
    $base = "HKCU:\Software\Classes\$protocol"
    if (-not (Test-Path $base) -or -not (Get-ItemProperty -Path $base -Name 'URL Protocol' -ErrorAction SilentlyContinue)) {
        New-Item -Path $base -Force | Out-Null
        Set-ItemProperty -Path $base -Name '(default)' -Value 'URL:Claude Code Focus'
        Set-ItemProperty -Path $base -Name 'URL Protocol' -Value ''
        $cmdKey = Join-Path $base 'shell\open\command'
        New-Item -Path $cmdKey -Force | Out-Null
        $cmd = "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$focusScript`""
        Set-ItemProperty -Path $cmdKey -Name '(default)' -Value $cmd
    }
}
catch { }

try {
    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'

    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    # Build the toast manually so we can set protocol activation on click.
    $escaped = [System.Security.SecurityElement]::Escape($Message)
    $xml = @"
<toast activationType="protocol" launch="$protocol`://focus">
  <visual>
    <binding template="ToastGeneric">
      <text>Claude Code</text>
      <text>$escaped</text>
    </binding>
  </visual>
</toast>
"@

    $template = [Windows.Data.Xml.Dom.XmlDocument]::new()
    $template.LoadXml($xml)

    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
}
catch {
    # Fall back to a tray balloon if the WinRT toast API is unavailable.
    Add-Type -AssemblyName System.Windows.Forms
    $balloon = New-Object System.Windows.Forms.NotifyIcon
    $balloon.Icon = [System.Drawing.SystemIcons]::Information
    $balloon.BalloonTipTitle = 'Claude Code'
    $balloon.BalloonTipText = $Message
    $balloon.Visible = $true
    $balloon.ShowBalloonTip(5000)
    Start-Sleep -Milliseconds 6000
    $balloon.Dispose()
}
