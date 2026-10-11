"""Real deployment control flow with synthetic OS/health responses, no host effects."""
from argparse import Namespace
from contextlib import ExitStack
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import deploy_core as deploy
from tests.test_core_release_tool import NGINX

SHA = 'a' * 40
CANARY = 'PRIVATE_EXCEPTION_BODY_MUST_NOT_BE_RECORDED'


class CoreDeploymentFailures(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixed = self.root / SHA
        self.fixed.mkdir()
        self.gate = self.root / 'maintenance.flag'
        self.gate.touch()
        self.nginx = self.root / 'nginx.conf'
        self.args = Namespace(commit=SHA, release_dir=str(self.fixed), env_file=[], acceptance='synthetic')
        self.states = {name: 'inactive' for name in deploy.CORE_WRITERS}
        self.states['mingjingtai.service'] = 'active'
        self.files = {name: 'disabled' for name in deploy.CORE_BOOT_WRITERS}
        self.files['mingjingtai.service'] = 'enabled'
        self.commands = []
        self.failed_commands = set()
        self.original = RuntimeError(CANARY)
        self.stack = ExitStack()
        for name, value in {'NGINX': str(self.nginx), 'MAINTENANCE': str(self.gate),
                            'MAINTENANCE_HTML': str(self.root / 'maintenance.html'), 'BACKUP_ROOT': str(self.root / 'backups')}.items():
            self.stack.enter_context(patch.object(deploy, name, value))
        self.nginx.write_text(deploy.render_nginx(NGINX), encoding='utf-8')
        self.stack.enter_context(patch.object(deploy, 'require_host'))
        self.verify = self.stack.enter_context(patch.object(deploy, 'verify_release', return_value=self.fixed))
        self.stack.enter_context(patch.object(deploy, 'evidence', return_value={}))
        self.stack.enter_context(patch.object(deploy, 'verify_legacy_disabled'))
        self.stack.enter_context(patch.object(deploy, 'verify_hermes_skill'))
        self.environment = self.stack.enter_context(patch.object(deploy, 'load_environment', return_value={'MINGJING_TOKEN': 'synthetic'}))
        self.stack.enter_context(patch.object(deploy, 'command', side_effect=self.command))
        self.stack.enter_context(patch.object(deploy.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(json.dumps({
            'ok': True, 'context_version': 'core3.0', 'database': 'postgresql', 'runtime': 'langgraph'}).encode())))

    def tearDown(self):
        self.stack.close()
        self.temporary.cleanup()

    def command(self, argv, **kwargs):
        self.commands.append(tuple(argv))
        if argv == ['nginx', '-t'] and ('nginx', '-t') in self.failed_commands:
            raise self.original
        if argv[0] != 'systemctl':
            return None
        operation = argv[1]
        if operation == 'show':
            name = argv[2]
            if '--property=WorkingDirectory' in argv:
                return str(self.fixed)
            return self.states[name] if '--property=ActiveState' in argv else self.files[name]
        if operation == 'enable':
            # Simulate a partial --now start before systemctl reports failure.
            self.states['zhiming-core-feishu.service'] = 'active'
            self.files['zhiming-core-feishu.service'] = 'enabled'
            if ('enable', 'partial') in self.failed_commands:
                raise self.original
            self.states['zhiming-core-reports.timer'] = 'active'
            self.files['zhiming-core-reports.timer'] = 'enabled'
            return None
        name = argv[-1]
        if (operation, name) in self.failed_commands:
            raise self.original
        if operation == 'disable':
            self.states[name] = 'inactive';self.files[name] = 'disabled'
        elif operation == 'stop':
            self.states[name] = 'inactive'
        return None

    def backup(self, args):
        self.assertTrue(all(self.states[name] == 'inactive' for name in deploy.CORE_WRITERS))
        self.assertTrue(all(self.files[name] == 'disabled' for name in deploy.CORE_BOOT_WRITERS))
        return {'maintenance': True, 'writers_stopped': True, 'latest_revocations_retained': 'synthetic-backup'}

    def failure_record(self):
        paths = list((self.root / 'backups').glob('*-publish-failure-*/failure.json'))
        self.assertEqual(len(paths), 1)
        record = json.loads(paths[0].read_text(encoding='utf-8'))
        self.assertNotIn(CANARY, json.dumps(record))
        self.assertFalse(record['rollback_complete']);self.assertFalse(record['automatic_retry_performed'])
        return record

    def assert_all_stopped(self):
        self.assertTrue(self.gate.is_file())
        self.assertTrue(all(self.states[name] == 'inactive' for name in deploy.CORE_WRITERS))
        self.assertTrue(all(self.files[name] == 'disabled' for name in deploy.CORE_BOOT_WRITERS))
        for name in deploy.CORE_WRITERS:
            self.assertIn(('systemctl', 'stop', name), self.commands)

    def test_nginx_precheck_happens_before_any_enable_and_failure_is_closed(self):
        self.failed_commands.add(('nginx', '-t'))
        with patch.object(deploy, 'maintenance', side_effect=self.backup), self.assertRaises(RuntimeError) as caught:
            deploy.publish(self.args)
        self.assertIs(caught.exception, self.original)
        self.assertFalse(any(command[1:2] == ('enable',) for command in self.commands))
        self.assert_all_stopped()
        self.assertTrue(self.failure_record()['cleanup']['latest_backup_completed'])

    def test_partial_enable_failure_stops_all_and_preserves_original_error(self):
        self.failed_commands.add(('enable', 'partial'))
        with patch.object(deploy, 'maintenance', side_effect=self.backup), self.assertRaises(RuntimeError) as caught:
            deploy.publish(self.args)
        self.assertIs(caught.exception, self.original)
        first_enable = next(index for index, command in enumerate(self.commands) if command[1:2] == ('enable',))
        self.assertLess(self.commands.index(('nginx', '-t')), first_enable)
        self.assert_all_stopped();self.assertTrue(self.failure_record()['cleanup']['cleanup_complete'])

    def test_maintenance_flag_unlink_failure_recreates_gate_and_disables_boot_writers(self):
        ordinary_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            if path == self.gate:
                raise self.original
            return ordinary_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', unlink), patch.object(deploy, 'maintenance', side_effect=self.backup), self.assertRaises(RuntimeError) as caught:
            deploy.publish(self.args)
        self.assertIs(caught.exception, self.original)
        self.assert_all_stopped();self.assertTrue(self.failure_record()['cleanup']['latest_backup_completed'])

    def test_failed_writer_stop_does_not_skip_others_or_dump_a_moving_ledger(self):
        self.failed_commands.update({('enable', 'partial'), ('disable', 'zhiming-core-feishu.service'),
                                     ('stop', 'zhiming-core-feishu.service')})
        with patch.object(deploy, 'maintenance') as backup, self.assertRaises(RuntimeError) as caught:
            deploy.publish(self.args)
        self.assertIs(caught.exception, self.original);backup.assert_not_called()
        for name in deploy.CORE_WRITERS:
            self.assertIn(('systemctl', 'stop', name), self.commands)
        cleanup = self.failure_record()['cleanup']
        self.assertFalse(cleanup['writers_stopped']);self.assertFalse(cleanup['cleanup_complete'])
        self.assertFalse(cleanup['latest_backup_attempted']);self.assertEqual(self.states['mingjingtai.service'], 'inactive')

    def test_install_rejects_external_writer_before_migration_or_environment_load(self):
        self.states['zhiming-core-reports.service'] = 'active'
        with self.assertRaisesRegex(ValueError, 'external writers must be inactive'):
            deploy.install(self.args)
        self.environment.assert_not_called()
        self.assertFalse(any(command[0].endswith('python') for command in self.commands))

    def test_partial_maintenance_cannot_report_stopped_or_call_database_backup(self):
        self.states['zhiming-core-feishu.service'] = 'active'
        self.files['zhiming-core-feishu.service'] = 'enabled'
        self.failed_commands.update({('disable', 'zhiming-core-feishu.service'), ('stop', 'zhiming-core-feishu.service')})
        self.verify.reset_mock()
        with self.assertRaisesRegex(ValueError, 'shutdown incomplete'):
            deploy.maintenance(self.args)
        self.verify.assert_not_called();self.environment.assert_not_called()
        self.assertTrue(self.gate.is_file())
        self.assertEqual(self.states['mingjingtai.service'], 'inactive');self.assertEqual(self.files['mingjingtai.service'], 'disabled')
        for name in deploy.CORE_WRITERS:
            self.assertIn(('systemctl', 'stop', name), self.commands)

    def test_runtime_only_mask_cannot_be_reported_as_reboot_safe(self):
        ordinary = self.command
        def runtime_mask(argv, **kwargs):
            if argv[:3] == ['systemctl', 'show', 'zhiming-core-feishu.service'] and '--property=UnitFileState' in argv:
                return 'masked-runtime'
            return ordinary(argv, **kwargs)
        with patch.object(deploy, 'command', side_effect=runtime_mask):
            shutdown = deploy.stop_core_writers()
        self.assertTrue(shutdown['writers_stopped'])
        self.assertFalse(shutdown['boot_writers_disabled']);self.assertFalse(shutdown['cleanup_complete'])


if __name__ == '__main__':
    unittest.main()
