import unittest
from unittest.mock import patch

from deploy.smoke import check


class ReleaseSmoke(unittest.TestCase):
    @patch('deploy.smoke.read')
    def test_frontend_must_match_backend_revision(self, read):
        read.side_effect = [b'{"status":"ok","revision":"good"}', b'old\n']
        with self.assertRaisesRegex(ValueError, 'frontend revision'):
            check('http://frontend', 'good', require_frontend=True)
