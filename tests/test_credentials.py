import ctypes
from ctypes import wintypes
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if 'spanish_helper' not in sys.modules:
    package = types.ModuleType('spanish_helper')
    package.__path__ = [str(ROOT / 'spanish_helper')]
    sys.modules['spanish_helper'] = package
credentials = importlib.import_module('spanish_helper.credentials')


class CredentialTests(unittest.TestCase):
    def test_targets_are_profile_scoped_and_contain_no_key_or_profile_name(self):
        first = credentials._target(str(ROOT / 'profile-alice'))
        second = credentials._target(str(ROOT / 'profile-bob'))
        self.assertTrue(first.startswith('AnkiSpanishHelper/OpenAI/'))
        self.assertEqual(first, credentials._target(str(ROOT / 'profile-alice')))
        self.assertNotEqual(first, second)
        self.assertNotIn('alice', first)
        with self.assertRaises(credentials.CredentialStoreError):
            credentials._target('')

    def test_save_uses_generic_credential_and_local_user_persistence(self):
        captured = {}
        def write(pointer, flags):
            value = ctypes.cast(pointer, ctypes.POINTER(credentials._Credential)).contents
            captured.update(type=value.Type, target=value.TargetName, persist=value.Persist,
                            secret=ctypes.string_at(value.CredentialBlob, value.CredentialBlobSize).decode('utf-8'), flags=flags)
            return True
        api = types.SimpleNamespace(CredWriteW=Mock(side_effect=write))
        with patch.object(credentials, 'supported', return_value=True), patch.object(credentials, '_api', return_value=api):
            credentials.save_key('profile-one', '  synthetic-test-key  ')
        self.assertEqual(captured['secret'], 'synthetic-test-key')
        self.assertEqual(captured['type'], 1)
        self.assertEqual(captured['persist'], 2)
        self.assertEqual(captured['flags'], 0)
        self.assertEqual(captured['target'], credentials._target('profile-one'))

    def test_save_rejects_blank_and_oversized_keys_without_native_call(self):
        with patch.object(credentials, 'supported', return_value=True), patch.object(credentials, '_api') as api:
            for key in (' ', 'x' * 2561):
                with self.assertRaises(credentials.CredentialStoreError):
                    credentials.save_key('profile-one', key)
            api.assert_not_called()

    def test_load_decodes_and_always_frees_the_native_buffer(self):
        for secret in (b'synthetic-test-key', b'\xff'):
            with self.subTest(valid=secret != b'\xff'):
                blob = ctypes.create_string_buffer(secret)
                value = credentials._Credential()
                value.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(wintypes.BYTE))
                value.CredentialBlobSize = len(secret)
                def read(target, kind, flags, output):
                    ctypes.cast(output, ctypes.POINTER(ctypes.POINTER(credentials._Credential)))[0] = ctypes.pointer(value)
                    return True
                api = types.SimpleNamespace(CredReadW=Mock(side_effect=read), CredFree=Mock())
                with patch.object(credentials, 'supported', return_value=True), patch.object(credentials, '_api', return_value=api):
                    if secret == b'\xff':
                        with self.assertRaises(credentials.CredentialStoreError):
                            credentials.load_key('profile-one')
                    else:
                        self.assertEqual(credentials.load_key('profile-one'), 'synthetic-test-key')
                api.CredFree.assert_called_once()

    def test_missing_key_is_normal_but_other_native_failures_are_reported(self):
        api = types.SimpleNamespace(CredReadW=Mock(return_value=False), CredDeleteW=Mock(return_value=False),
                                    CredWriteW=Mock(return_value=False))
        with patch.object(credentials, 'supported', return_value=True), patch.object(credentials, '_api', return_value=api):
            with patch.object(credentials, '_last_error', return_value=1168):
                self.assertEqual(credentials.load_key('profile-one'), '')
                credentials.delete_key('profile-one')
            with patch.object(credentials, '_last_error', return_value=5):
                with self.assertRaises(credentials.CredentialStoreError):
                    credentials.load_key('profile-one')
                with self.assertRaises(credentials.CredentialStoreError):
                    credentials.delete_key('profile-one')
            with self.assertRaises(credentials.CredentialStoreError) as error:
                credentials.save_key('profile-one', 'synthetic-test-key')
            self.assertNotIn('synthetic-test-key', str(error.exception))

    def test_unsupported_platform_uses_no_plaintext_fallback(self):
        with patch.object(credentials, 'supported', return_value=False), patch.object(credentials, '_api') as api:
            self.assertEqual(credentials.load_key('profile-one'), '')
            credentials.delete_key('profile-one')
            with self.assertRaises(credentials.CredentialStoreError):
                credentials.save_key('profile-one', 'synthetic-test-key')
            api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
