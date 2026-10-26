"""Windows OS cryptography for protected OAuth storage and OIDC signatures."""
import ctypes
from ctypes import wintypes
import hashlib
import struct
import sys


class AuthError(RuntimeError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    if sys.platform != 'win32':
        raise AuthError('El acceso con ChatGPT de este complemento requiere Windows.')
    crypt = ctypes.WinDLL('crypt32.dll', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32.dll', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = _Blob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise AuthError('Windows no puede proteger o leer la sesión de ChatGPT. Vuelve a iniciar sesión.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)
        ctypes.memset(buffer, 0, len(buffer))


def verify_rs256(message, signature, modulus, exponent):
    """Verify RS256 with Windows CNG, not a custom cryptographic implementation."""
    if sys.platform != 'win32' or not 256 <= len(modulus) <= 1024 or not 1 <= len(exponent) <= 4:
        raise AuthError('No se puede verificar la identidad de ChatGPT en este equipo.')
    api = ctypes.WinDLL('bcrypt.dll')
    handle = ctypes.c_void_p
    api.BCryptOpenAlgorithmProvider.argtypes = [ctypes.POINTER(handle), wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    api.BCryptImportKeyPair.argtypes = [handle, handle, wintypes.LPCWSTR, ctypes.POINTER(handle), ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    api.BCryptVerifySignature.argtypes = [handle, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    api.BCryptDestroyKey.argtypes = [handle]
    api.BCryptCloseAlgorithmProvider.argtypes = [handle, wintypes.DWORD]
    for name in ('BCryptOpenAlgorithmProvider', 'BCryptImportKeyPair', 'BCryptVerifySignature', 'BCryptDestroyKey', 'BCryptCloseAlgorithmProvider'):
        getattr(api, name).restype = ctypes.c_long
    algorithm, key = handle(), handle()
    if api.BCryptOpenAlgorithmProvider(ctypes.byref(algorithm), 'RSA', None, 0) != 0:
        raise AuthError('Windows no puede verificar la firma de ChatGPT.')
    try:
        blob = struct.pack('<6I', 0x31415352, len(modulus) * 8, len(exponent), len(modulus), 0, 0) + exponent + modulus
        public = ctypes.create_string_buffer(blob)
        if api.BCryptImportKeyPair(algorithm, None, 'RSAPUBLICBLOB', ctypes.byref(key), public, len(blob), 0) != 0:
            raise AuthError('La clave pública de ChatGPT no es válida.')
        class Padding(ctypes.Structure):
            _fields_ = [('algorithm', wintypes.LPCWSTR)]
        padding = Padding('SHA256')
        digest = hashlib.sha256(message).digest()
        digest_buffer, signature_buffer = ctypes.create_string_buffer(digest), ctypes.create_string_buffer(signature)
        if api.BCryptVerifySignature(key, ctypes.byref(padding), digest_buffer, len(digest), signature_buffer, len(signature), 2) != 0:
            raise AuthError('La firma de la identidad de ChatGPT no es válida.')
    finally:
        if key:
            api.BCryptDestroyKey(key)
        api.BCryptCloseAlgorithmProvider(algorithm, 0)
