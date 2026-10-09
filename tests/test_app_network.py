# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license in LICENSE.
"""Offline evidence/transport regressions, not emulator execution."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
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


class ServiceReadinessTest(unittest.TestCase):
    def test_layout_requires_real_widget_not_empty_root(self):
        for node in [{}, [], {'attributes':{'bounds':'[0,0][3120,2080]','type':''}},
                     {'children':[]}, {'attributes':'invalid'}, 'error']:
            self.assertFalse(runner.layout_has_widgets(node))
        self.assertTrue(runner.layout_has_widgets({'children':[
            {'attributes':{'bounds':'[0,0][100,50]','type':'Text'}}]}))

    def test_ui_wait_is_read_only_and_retries_empty_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            app=runner.AppRunner(directory,directory)
            tree=Path(directory)/'layout.json'
            tree.write_text(json.dumps({'children':[{'attributes':{'type':'Text','bounds':'[0,0][10,10]'}}]}))
            with mock.patch.object(app,'capture_ui',side_effect=[{}, {'png':Path(directory)/'screen.png','json':tree}]) as capture, \
                 mock.patch.object(runner.time,'sleep'), mock.patch.object(app,'shell') as shell:
                app.wait_for_app_ui()
                self.assertEqual(capture.call_count,2)
                shell.assert_not_called()

    def test_ui_wait_deadline_never_launches_or_injects(self):
        with tempfile.TemporaryDirectory() as directory:
            app=runner.AppRunner(directory,directory)
            with mock.patch.object(runner.time,'monotonic',side_effect=[0,301]), \
                 mock.patch.object(app,'diagnose_app'), mock.patch.object(app,'shell') as shell:
                with self.assertRaisesRegex(runner.Failure,'no input injected'):
                    app.wait_for_app_ui()
                shell.assert_not_called()

    def test_normal_app_uses_xcb_but_shell_default_stays_headless(self):
        with tempfile.TemporaryDirectory() as directory:
            app=runner.AppRunner(directory,directory)
            shell=runner.Runner(directory,directory)
            self.assertFalse(app.headless)
            self.assertEqual(app.env()['QT_QPA_PLATFORM'],'xcb')
            self.assertNotIn('-noWindow',app.start_command())
            self.assertTrue(shell.headless)
            self.assertEqual(shell.env()['QT_QPA_PLATFORM'],'offscreen')
            self.assertIn('-noWindow',shell.start_command())

    def test_only_successful_bundle_list_proves_readiness(self):
        self.assertTrue(runner.app_services_ready("ID: 100:\n\tcom.ohos.launcher\n\tcom.ohos.settings\n"))
        for text in ["", "error: failed to execute your command.\n", "ID: 100:\n",
                     "dump failed\n", "\tcom.ohos.launcher\n", "ID: 100:\n\tcom.ohos.launcher\nerror: partial"]:
            with self.subTest(text=text): self.assertFalse(runner.app_services_ready(text))

    def test_service_probe_retries_before_install(self):
        with tempfile.TemporaryDirectory() as directory:
            app=runner.AppRunner(directory,directory)
            replies=[(0,"error: failed to execute your command.\n"),
                     (0,"ID: 100:\n\tcom.ohos.launcher\n"),(0,"true\n"),(0,"hilog help")]
            with mock.patch.object(app,'shell',side_effect=replies) as shell, mock.patch.object(runner.time,'sleep'):
                app.wait_for_app_services()
            self.assertEqual(shell.call_args_list[0].args[1], 'bm dump -a')
            self.assertEqual(shell.call_args_list[1].args[1], 'bm dump -a')
            self.assertTrue(any(r['name']=='app-services' for r in app.results))
            self.assertNotIn('install', repr(shell.call_args_list))

    def test_ui_capture_uses_read_only_commands_and_detects_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            app=runner.AppRunner(directory,directory)
            with mock.patch.object(app,'shell',return_value=(0,'')) as shell, \
                 mock.patch.object(app,'run',return_value=(0,'')):
                app.capture_ui('test-screen')
            commands=[call.args[1] for call in shell.call_args_list]
            self.assertEqual(len(commands),2)
            self.assertTrue(commands[0].startswith('uitest screenCap -p /data/local/tmp/'))
            self.assertTrue(commands[1].startswith('uitest dumpLayout -p /data/local/tmp/'))
            self.assertNotIn('uiInput',repr(commands))
            self.assertEqual(sum(r['name']=='app-ui-evidence-error' for r in app.results),2)

    def test_expired_readiness_cannot_install(self):
        with tempfile.TemporaryDirectory() as directory:
            app=runner.AppRunner(directory,directory)
            with mock.patch.object(runner.time,'monotonic',side_effect=[0,301]), \
                 mock.patch.object(app,'diagnose_app') as diagnose, mock.patch.object(app,'shell') as shell:
                with self.assertRaisesRegex(runner.Failure,'HAP was not installed'):
                    app.wait_for_app_services()
                shell.assert_not_called()
                diagnose.assert_called_once()


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
