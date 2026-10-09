# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license in LICENSE.
"""Offline evidence/transport regressions, not emulator execution."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

runner = load('app_runner', ROOT / 'scripts/app/run.py')
hap = load('validate_hap', ROOT / 'scripts/app/validate_hap.py')
TOKEN = 'a' * 32


def good():
    identity = {'goos': 'openharmony', 'goarch': 'amd64', 'uid': 20010001, 'pid': 202}
    return {'schema_version': 1, 'core_revision': 'b637b8617624655906b737977f50de5280bf7f65',
            'identity': identity, 'overall_pass': True, 'failed': [],
            'checks': [{'name': name, 'passed': True, 'process': {'uid': identity['uid'], 'pid': identity['pid']}}
                       for name in sorted(runner.REQUIRED)]}


class ReportTest(unittest.TestCase):
    def test_valid_chunks_are_assembled_in_numeric_order(self):
        encoded = json.dumps({'token': TOKEN, 'report': good()})
        parts = [encoded[i:i+100] for i in range(0,len(encoded),100)]
        text = '\n'.join(f'timestamp GO_HMOS_APP_{TOKEN}_{i}_{len(parts)}:{s}'
                         for i,s in reversed(list(enumerate(parts))))
        self.assertEqual(runner.extract_report(text, TOKEN), good())

    def test_missing_chunk_never_passes(self):
        self.assertIsNone(runner.extract_report(f'GO_HMOS_APP_{TOKEN}_0_2:{{', TOKEN))

    def test_other_run_token_never_passes(self):
        self.assertIsNone(runner.extract_report('GO_HMOS_APP_'+'b'*32+'_0_1:{}', TOKEN))

    def test_identical_repeated_dump_does_not_look_like_two_reports(self):
        line = f'GO_HMOS_APP_{TOKEN}_0_1:' + json.dumps({'token':TOKEN,'report':good()})
        self.assertEqual(runner.extract_report(line+'\n'+line, TOKEN), good())

    def test_bad_chunks_fail(self):
        for text in [f'GO_HMOS_APP_{TOKEN}_0_1:{{',
                     f'GO_HMOS_APP_{TOKEN}_0_1:a\nGO_HMOS_APP_{TOKEN}_0_1:b',
                     f'GO_HMOS_APP_{TOKEN}_2_1:a',
                     f'GO_HMOS_APP_ERROR_{TOKEN}:dlopen failed']:
            with self.subTest(text=text), self.assertRaises(runner.Failure):
                runner.extract_report(text,TOKEN)

    def test_valid_report(self):
        runner.validate_report(good())

    def test_identity_missing_check_and_failures_rejected(self):
        mutations = [lambda r:r['identity'].update(goos='linux'),
                     lambda r:r['identity'].update(uid=0),
                     lambda r:r.update(schema_version=2),
                     lambda r:r.update(core_revision='0'*40),
                     lambda r:r['checks'][0]['process'].update(uid=12345),
                     lambda r:r['checks'][0]['process'].update(pid=999),
                     lambda r:r.update(failed=['unexpected']),
                     lambda r:r['checks'].pop(),
                     lambda r:r['checks'].append(r['checks'][0]),
                     lambda r:r['checks'][0].update(passed=False),
                     lambda r:r.update(overall_pass=False)]
        for change in mutations:
            report = good(); change(report)
            with self.assertRaises(runner.Failure):
                runner.validate_report(report)

    def test_source_declares_only_internet(self):
        module=json.loads((ROOT/'testdata/app-host/entry/src/main/module.json5').read_text())
        self.assertEqual(module['module']['requestPermissions'],[{'name':'ohos.permission.INTERNET'}])
        profile=json.loads((ROOT/'testdata/app-host/build-profile.json5').read_text())
        self.assertEqual(profile['app']['signingConfigs'],[])
        self.assertNotIn('signingConfig',profile['app']['products'][0])


class PackedHapTest(unittest.TestCase):
    def test_actual_packed_permissions_checked(self):
        module={'app':{'bundleName':'org.gohmos.networktest','debug':True,'minAPIVersion':60101024,
                       'targetAPIVersion':60101024,'compileSdkType':'HarmonyOS'},
                'module':{'virtualMachine':'ark24.0.0.0','requestPermissions':[{'name':'ohos.permission.INTERNET'}]}}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'entry.hap'
            for extra in [False,True]:
                if extra: module['module']['requestPermissions'].append({'name':'ohos.permission.GET_NETWORK_INFO'})
                with zipfile.ZipFile(path,'w') as z:
                    z.writestr('module.json',json.dumps(module))
                    for name in ['libgo_app_network.so','libgohmos.so']:
                        z.writestr('libs/x86_64/'+name,b'\x7fELF\x02\x01'+b'\x00'*12+(62).to_bytes(2,'little'))
                if extra:
                    with self.assertRaises(ValueError): hap.validate(path)
                else: self.assertEqual(hap.validate(path),module)


    def test_wrong_packed_api_or_vm_rejected(self):
        original={'app':{'bundleName':'org.gohmos.networktest','debug':True,
                         'minAPIVersion':60101024,'targetAPIVersion':60101024,'compileSdkType':'HarmonyOS'},
                  'module':{'virtualMachine':'ark24.0.0.0',
                            'requestPermissions':[{'name':'ohos.permission.INTERNET'}]}}
        for section,key,value in [('app','minAPIVersion',24),('app','minAPIVersion',60101023),
                                  ('app','targetAPIVersion',26000000),('app','compileSdkType','OpenHarmony'),
                                  ('module','virtualMachine','ark26.0.0.0')]:
            module=copy.deepcopy(original); module[section][key]=value
            with self.subTest(key=key,value=value), tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'wrong.hap'
                with zipfile.ZipFile(path,'w') as z:
                    z.writestr('module.json',json.dumps(module))
                with self.assertRaisesRegex(ValueError,'HarmonyOS 6.1.1'):
                    hap.validate(path)


if __name__=='__main__': unittest.main()
