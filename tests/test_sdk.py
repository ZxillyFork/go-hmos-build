"""Offline packaging contract tests; these never count as compiler validation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('sdk_metadata', ROOT / 'scripts/sdk/metadata.py')
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


class SDKMetadataTest(unittest.TestCase):
    def test_real_release_config(self):
        release, source = metadata.config()
        self.assertTrue(release['release_tag'].startswith('go1.27.2-hmos.'))
        self.assertEqual(source['revision'], '7ea2c37368c408d68804c9bda8f9e74b03fe4122')

    def test_moving_source_and_stock_version_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            release = json.loads((ROOT / 'sdk-release.json').read_text())
            source = json.loads((ROOT / 'source.json').read_text())
            for changed, field, value in ((source, 'revision', 'hmos-release-branch.go1.27'),
                                          (release, 'go_version', 'go1.27.2'),
                                          (release, 'release_tag', 'latest'),
                                          (release, 'host_arch', 'arm64')):
                with self.subTest(field=field):
                    previous = changed[field]
                    changed[field] = value
                    (root / 'sdk-release.json').write_text(json.dumps(release))
                    (root / 'source.json').write_text(json.dumps(source))
                    with patch.object(metadata, 'ROOT', root), self.assertRaises(ValueError):
                        metadata.config()
                    changed[field] = previous

    def test_manifest_hash_and_source_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = 'go1.27.2-hmos-devel.linux-amd64.tar.gz'
            (root / archive).write_bytes(b'offline fixture')
            data = metadata.provenance()
            (root / 'provenance.json').write_text(json.dumps(data))
            result = metadata.manifest(root)
            self.assertEqual(result['sha256'], hashlib.sha256(b'offline fixture').hexdigest())
            self.assertFalse(result['native_sdk_included'])
            self.assertEqual(result['source_commit'], '7ea2c37368c408d68804c9bda8f9e74b03fe4122')
            self.assertIn('/releases/download/go1.27.2-hmos.5/', result['download_url'])

    def test_workflow_uses_real_setup_go_custom_input(self):
        workflow = (ROOT / '.github/workflows/linux-sdk.yml').read_text()
        self.assertEqual(workflow.count('uses: actions/setup-go@924ae3a1cded613372ab5595356fb5720e22ba16'), 3)
        self.assertIn('go-download-base-url: http://127.0.0.1:8765', workflow)
        self.assertIn('go-download-base-url: https://github.com/ZxillyFork/go-hmos-build/releases/download/', workflow)
        self.assertIn('--prerelease --latest=false', workflow)
        self.assertNotIn('--clobber', workflow)
        self.assertIn('sha256sum --check SHA256SUMS', workflow)
        self.assertIn('GOTOOLCHAIN: local', workflow)

    def test_package_script_never_copies_native_sdk(self):
        script = (ROOT / 'scripts/sdk/package.sh').read_text()
        self.assertIn('git -C "$root" archive HEAD', script)
        self.assertIn('"$root/pkg/tool/linux_amd64"', script)
        for generated in ('src/cmd/cgo/zdefaultcc.go', 'src/cmd/go/internal/cfg/zdefaultcc.go',
                          'src/cmd/internal/objabi/zbootstrap.go', 'src/internal/buildcfg/zbootstrap.go',
                          'src/internal/runtime/sys/zversion.go', 'src/time/tzdata/zzipdata.go'):
            self.assertIn(generated, script)
        verification = (ROOT / 'scripts/sdk/verify.sh').read_text()
        self.assertIn('export GOCACHE="$work/cache"', verification)
        self.assertIn('go build time/tzdata internal/buildcfg cmd/internal/objabi cmd/cgo cmd/compile cmd/go', verification)
        self.assertNotIn('cp -a "$root/.', script)
        result = subprocess.run(['bash', '-n', str(ROOT / 'scripts/sdk/package.sh')], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
