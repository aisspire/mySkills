[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Target,

    [ValidateNotNullOrEmpty()]
    [string]$UserName = "database-schema-bootstrap"
)

$credentialTypeGeneric = 1
$credentialPersistLocalMachine = 2

if (-not ([type]::GetType("DbSchemaBootstrap.CredentialNative", $false))) {
    Add-Type -TypeDefinition @"
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

namespace DbSchemaBootstrap
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct Credential
    {
        public UInt32 Flags;
        public UInt32 Type;
        public string TargetName;
        public string Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public UInt32 CredentialBlobSize;
        public IntPtr CredentialBlob;
        public UInt32 Persist;
        public UInt32 AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias;
        public string UserName;
    }

    public static class CredentialNative
    {
        [DllImport("Advapi32.dll", EntryPoint = "CredWriteW", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool CredWrite(ref Credential userCredential, UInt32 flags);
    }
}
"@
}

$securePassword = Read-Host -Prompt "Database password for credential target '$Target'" -AsSecureString
if ($securePassword.Length -eq 0) {
    throw "Password cannot be empty."
}

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$passwordText = $null
$passwordBytes = @()
$blob = [IntPtr]::Zero

try {
    $passwordText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $passwordBytes = [Text.Encoding]::Unicode.GetBytes($passwordText)
    $blob = [Runtime.InteropServices.Marshal]::AllocHGlobal($passwordBytes.Length)
    [Runtime.InteropServices.Marshal]::Copy($passwordBytes, 0, $blob, $passwordBytes.Length)

    $credential = [DbSchemaBootstrap.Credential]::new()
    $credential.Flags = 0
    $credential.Type = $credentialTypeGeneric
    $credential.TargetName = $Target
    $credential.CredentialBlobSize = [uint32]$passwordBytes.Length
    $credential.CredentialBlob = $blob
    $credential.Persist = $credentialPersistLocalMachine
    $credential.AttributeCount = 0
    $credential.Attributes = [IntPtr]::Zero
    $credential.TargetAlias = $null
    $credential.UserName = $UserName

    $ok = [DbSchemaBootstrap.CredentialNative]::CredWrite([ref]$credential, 0)
    if (-not $ok) {
        $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw [ComponentModel.Win32Exception]::new($errorCode)
    }

    Write-Host "Stored database credential target: $Target"
}
finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if ($blob -ne [IntPtr]::Zero) {
        for ($i = 0; $i -lt $passwordBytes.Length; $i++) {
            [Runtime.InteropServices.Marshal]::WriteByte($blob, $i, 0)
        }
        [Runtime.InteropServices.Marshal]::FreeHGlobal($blob)
    }
    if ($securePassword -is [IDisposable]) {
        $securePassword.Dispose()
    }
}
