import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import set_advisor_key


class SetAdvisorKeyTests(unittest.TestCase):
    def setUp(self):
        self.env = Path(self.enterContext(tempfile.TemporaryDirectory())) / '.env'

    def test_replaces_duplicate_entries_preserving_other_lines(self):
        self.env.write_bytes(b'# local\r\nOTHER=value\r\nADVISOR_API_KEY=old\r\nADVISOR_API_KEY=older\r\n')
        set_advisor_key.save_key(self.env, 'test-key')
        self.assertEqual(self.env.read_bytes(), b'# local\r\nOTHER=value\r\nADVISOR_API_KEY=test-key\r\n')

    def test_creates_file_readable_by_backend(self):
        from advisor import vision_key
        set_advisor_key.save_key(self.env, 'test-key')
        with patch.dict(os.environ, {'ADVISOR_API_KEY': ''}), patch('advisor.__file__', str(self.env.with_name('advisor.py'))):
            self.assertEqual(vision_key(), 'test-key')

    def test_rejects_invalid_input_before_writing(self):
        for key in ('', 'not a key', 'abc\nOTHER=value', '"abc"'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                set_advisor_key.save_key(self.env, key)
        self.assertFalse(self.env.exists())

    def test_server_key_file_overrides_legacy_environment_and_can_be_rotated(self):
        secret = self.env.with_name('.advisor-api-key')
        with patch.dict(os.environ, {'ADVISOR_API_KEY_FILE': str(secret), 'ADVISOR_API_KEY': 'legacy-key'}):
            self.assertEqual(set_advisor_key.load_key(self.env), 'legacy-key')
            self.assertEqual(set_advisor_key.load_key(self.env, file_only=True), '')
            set_advisor_key.save_key(secret, 'server-key', raw=True)
            self.assertEqual(set_advisor_key.load_key(self.env), 'server-key')
            set_advisor_key.save_key(secret, 'rotated-key', raw=True)
            self.assertEqual(set_advisor_key.load_key(self.env), 'rotated-key')

    def test_dotenv_handles_bom_spaces_and_legacy_quotes(self):
        self.env.write_bytes(b'\xef\xbb\xbf  ADVISOR_API_KEY = "local-key"\r\n')
        with patch.dict(os.environ, {'ADVISOR_API_KEY_FILE': '', 'ADVISOR_API_KEY': ''}):
            self.assertEqual(set_advisor_key.load_key(self.env), 'local-key')
