from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from .config import PostgresProfile
from .errors import CredentialError


class CredentialAttribute(ctypes.Structure):
    _fields_ = [
        ("Keyword", wintypes.LPWSTR),
        ("Flags", wintypes.DWORD),
        ("ValueSize", wintypes.DWORD),
        ("Value", wintypes.LPBYTE),
    ]


class Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", wintypes.LPBYTE),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.POINTER(CredentialAttribute)),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def read_windows_credential(target: str) -> str:
    if os.name != "nt":
        raise CredentialError(
            "Windows Credential Manager is required for database credentials."
        )

    credential_pointer = ctypes.POINTER(Credential)()
    cred_read = ctypes.windll.advapi32.CredReadW
    cred_read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(Credential)),
    ]
    cred_read.restype = wintypes.BOOL

    if not cred_read(target, 1, 0, ctypes.byref(credential_pointer)):
        raise CredentialError("Database credential is unavailable.")

    try:
        credential = credential_pointer.contents
        raw = bytes(
            ctypes.string_at(
                credential.CredentialBlob,
                credential.CredentialBlobSize,
            )
        )
        try:
            return raw.decode("utf-16-le").rstrip("\x00")
        except UnicodeDecodeError:
            return raw.decode("utf-8")
    except Exception as exc:
        raise CredentialError("Database credential could not be decoded.") from exc
    finally:
        ctypes.windll.advapi32.CredFree(credential_pointer)


def read_profile_password(
    profile: PostgresProfile,
    reader=read_windows_credential,
) -> str:
    password = reader(profile.credential_target)
    if not password:
        raise CredentialError("Database credential is empty.")
    return password

