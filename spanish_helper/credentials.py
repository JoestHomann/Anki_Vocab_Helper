"""Profile-scoped API keys in Windows Credential Manager; no plaintext fallback."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import os
import sys


class CredentialStoreError(RuntimeError):
    pass


class _Credential(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD), ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR), ('Comment', wintypes.LPWSTR),
        ('LastWritten', wintypes.FILETIME), ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(wintypes.BYTE)), ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
        ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR),
    ]


def supported() -> bool:
    return sys.platform == 'win32'


def _target(profile_folder: str) -> str:
    if not profile_folder:
        raise CredentialStoreError('Abre un perfil de Anki antes de guardar la clave.')
    profile = os.path.normcase(os.path.abspath(profile_folder))
    digest = hashlib.sha256(profile.encode('utf-8')).hexdigest()
    return 'AnkiSpanishHelper/OpenAI/' + digest


def _api():
    try:
        api = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
    except (AttributeError, OSError):
        raise CredentialStoreError('No se puede acceder al Administrador de credenciales de Windows. Revisa tu sesión de Windows e inténtalo de nuevo; la clave guardada no se ha cambiado.') from None
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_Credential))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredDeleteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return api


def _last_error():
    return ctypes.get_last_error()


def load_key(profile_folder: str) -> str:
    if not supported():
        return ''
    api = _api()
    pointer = ctypes.POINTER(_Credential)()
    if not api.CredReadW(_target(profile_folder), 1, 0, ctypes.byref(pointer)):
        if _last_error() == 1168:  # ERROR_NOT_FOUND
            return ''
        raise CredentialStoreError('No se puede leer la clave guardada en Windows. Abre Herramientas → Spanish Helper para revisarla.')
    try:
        credential = pointer.contents
        if not 0 < credential.CredentialBlobSize <= 2560:
            raise CredentialStoreError('La clave guardada no es válida. Vuelve a introducirla en Spanish Helper.')
        return ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize).decode('utf-8')
    except UnicodeDecodeError:
        raise CredentialStoreError('La clave guardada no es válida. Vuelve a introducirla en Spanish Helper.') from None
    finally:
        api.CredFree(pointer)


def save_key(profile_folder: str, key: str):
    if not supported():
        raise CredentialStoreError('Recordar la clave está disponible en Windows. Puedes usarla solo durante esta sesión.')
    encoded = key.strip().encode('utf-8')
    if not encoded or len(encoded) > 2560:
        raise CredentialStoreError('Introduce una clave API válida para guardarla.')
    buffer = ctypes.create_string_buffer(encoded)
    credential = _Credential()
    credential.Type = 1  # CRED_TYPE_GENERIC
    credential.TargetName = _target(profile_folder)
    credential.Comment = 'Spanish Helper: OpenAI API key for this Anki profile'
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(wintypes.BYTE))
    credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE: current user, this computer
    credential.UserName = 'OpenAI'
    try:
        if not _api().CredWriteW(ctypes.byref(credential), 0):
            raise CredentialStoreError('Windows no ha podido guardar la clave. Inténtalo de nuevo o desmarca Recordar para usarla solo en esta sesión.')
    finally:
        ctypes.memset(buffer, 0, len(buffer))


def delete_key(profile_folder: str):
    if not supported():
        return
    if not _api().CredDeleteW(_target(profile_folder), 1, 0) and _last_error() != 1168:
        raise CredentialStoreError('Windows no ha podido olvidar la clave guardada. Inténtalo de nuevo antes de cerrar los ajustes.')
