# Invoked via the claude-code-focus:// protocol when a Claude Code toast is
# clicked. Reads the terminal window handle saved by notify.ps1 and brings that
# window to the foreground.
$ErrorActionPreference = 'SilentlyContinue'

$hwndFile = Join-Path $env:TEMP 'claude_terminal_hwnd.txt'
if (-not (Test-Path $hwndFile)) { return }

$raw = (Get-Content $hwndFile -Raw).Trim()
[int64]$hwndVal = 0
if (-not [int64]::TryParse($raw, [ref]$hwndVal) -or $hwndVal -eq 0) { return }
$hwnd = [IntPtr]$hwndVal

$sig = @'
using System;
using System.Runtime.InteropServices;
public static class Win {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
}
'@
Add-Type -TypeDefinition $sig

if (-not [Win]::IsWindow($hwnd)) { return }

# SW_RESTORE if minimized.
if ([Win]::IsIconic($hwnd)) { [Win]::ShowWindow($hwnd, 9) | Out-Null }

# Tapping ALT clears Windows' foreground lock so SetForegroundWindow succeeds
# even when the click activation comes from another process.
[Win]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)        # ALT down
[Win]::keybd_event(0x12, 0, 0x0002, [UIntPtr]::Zero)   # ALT up
[Win]::SetForegroundWindow($hwnd) | Out-Null
