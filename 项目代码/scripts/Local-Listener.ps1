function Get-LocalListener {
    param([int]$Port)

    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return $listener }

    # Some Windows builds report state 0 for an active loopback socket.
    $candidate = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -eq '127.0.0.1' -and $_.RemotePort -eq 0 -and
            $_.OwningProcess -gt 0 -and $_.CimInstanceProperties['State'].Value -eq 0 } |
        Select-Object -First 1
    if (!$candidate) { return }

    $client = [Net.Sockets.TcpClient]::new()
    try {
        $connect = $client.ConnectAsync('127.0.0.1', $Port)
        if ([System.Threading.Tasks.Task]::WaitAny(@($connect), 1000) -eq 0 -and $client.Connected) {
            return $candidate
        }
    } finally {
        $client.Dispose()
    }
}
