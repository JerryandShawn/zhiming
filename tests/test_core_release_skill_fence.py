"""Hermes maintenance gates and backup fences; no Linux host/model effects.

Native Linux flock/exec behavior is tested by the separate temporary-path
probe, not claimed by these portable control-flow tests.
"""
from argparse import Namespace
from contextlib import ExitStack,closing,contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import deploy_core as deploy
from tests.test_core_release_tool import NGINX

SHA='c'*40


class CapturedExec(BaseException):pass


class CoreSkillWriterFence(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.addCleanup(self.temporary.cleanup)
        self.gate=self.root/'gate';self.lock=self.root/'writer.lock';self.held=False;self.events=[]
        self.args=Namespace(commit=SHA,release_dir=str(self.root/'release'),env_file=[])
        for name,value in {'MAINTENANCE':str(self.gate),'MAINTENANCE_HTML':str(self.root/'gate.html'),
                           'SKILL_WRITER_LOCK':str(self.lock),'BACKUP_ROOT':str(self.root/'backups')}.items():
            self.stack.enter_context(patch.object(deploy,name,value))

    @contextmanager
    def fence(self,**kwargs):
        self.events.append(('lock',kwargs));self.assertFalse(self.held);self.held=True
        descriptor=os.open(self.lock,os.O_RDWR|os.O_CREAT,0o600)
        try:yield descriptor
        finally:
            os.close(descriptor);self.held=False;self.events.append(('unlock',None))

    def test_gate_rejects_before_release_env_or_exec(self):
        self.gate.touch()
        with patch.object(deploy,'verify_release') as verify,patch.object(deploy,'load_environment') as env,patch.object(os,'execv') as execute:
            with self.assertRaisesRegex(ValueError,'maintenance'):deploy.execute_hermes_core(self.args,['consult'])
            verify.assert_not_called();env.assert_not_called();execute.assert_not_called()

    def test_gate_is_rechecked_inside_shared_lock(self):
        @contextmanager
        def racing(**kwargs):
            self.gate.touch()
            with self.fence(**kwargs) as descriptor:yield descriptor
        with patch.object(deploy,'skill_writer_lock',side_effect=racing),patch.object(deploy,'verify_release') as verify,patch.object(os,'execv') as execute:
            with self.assertRaisesRegex(ValueError,'maintenance'):deploy.execute_hermes_core(self.args,['consult'])
            verify.assert_not_called();execute.assert_not_called()
        self.assertFalse(self.held)

    def test_exec_inherits_open_shared_fd_and_exact_argv(self):
        def execute(binary,argv):
            self.assertTrue(self.held)
            descriptors=[fd for fd in range(3,256) if self._same_descriptor(fd)]
            self.assertEqual(len(descriptors),1);self.assertTrue(os.get_inheritable(descriptors[0]))
            self.assertEqual(argv,[str(self.root/'release/venv/core/bin/python'),str(self.root/'release/hermes/core_consultation.py'),'consult','literal;$(no_shell)'])
            self.assertEqual(binary,argv[0]);raise CapturedExec()
        with patch.object(deploy,'skill_writer_lock',side_effect=self.fence),patch.object(deploy,'verify_release',return_value=self.root/'release'),patch.object(deploy,'load_environment',return_value={'SYNTHETIC':'fixed'}),patch.dict(os.environ,{},clear=True),patch.object(os,'execv',side_effect=execute):
            with self.assertRaises(CapturedExec):deploy.execute_hermes_core(self.args,['consult','literal;$(no_shell)'])
        self.assertFalse(self.held);self.assertEqual(self.events[0][1],{'timeout':0})

    def _same_descriptor(self,fd):
        try:return os.fstat(fd).st_ino==self.lock.stat().st_ino
        except OSError:return False

    def test_busy_shared_lock_cannot_execute_or_load_configuration(self):
        with patch.object(deploy,'skill_writer_lock',side_effect=TimeoutError('synthetic busy')),patch.object(deploy,'verify_release') as verify,patch.object(os,'execv') as execute:
            with self.assertRaises(TimeoutError):deploy.execute_hermes_core(self.args,['consult'])
            verify.assert_not_called();execute.assert_not_called()

    def test_native_lock_calls_are_bounded_and_close_fd_on_timeout(self):
        attempts=[]
        def flock(descriptor,operation):attempts.append((descriptor,operation));raise BlockingIOError()
        backend=SimpleNamespace(LOCK_EX=2,LOCK_SH=1,LOCK_NB=4,flock=flock)
        with patch.dict(sys.modules,{'fcntl':backend}),patch.object(os,'O_NOFOLLOW',getattr(os,'O_NOFOLLOW',0),create=True),patch.object(os,'fchmod',create=True),patch.object(deploy.time,'monotonic',side_effect=[0,1]),patch.object(deploy.time,'sleep') as sleep:
            with self.assertRaises(TimeoutError):
                with deploy.skill_writer_lock(exclusive=True,timeout=0):self.fail('busy fence entered')
        self.assertEqual(attempts[0][1],6);sleep.assert_not_called()
        with self.assertRaises(OSError):os.fstat(attempts[0][0])

    def test_maintenance_holds_exclusive_lock_until_dump_and_journal_complete(self):
        self.gate.touch();nginx=self.root/'nginx';nginx.write_text(NGINX)
        cleanup={'cleanup_complete':True,'writers_stopped':True,'errors':[]}
        def command(argv,**kwargs):
            self.assertTrue(self.held)
            if '--property=KillMode' in argv:return 'control-group'
            if '--property=SendSIGKILL' in argv:return 'yes'
            if len(argv)>1 and argv[1]=='-c':
                self.events.append(('backup',None))
                for key in ('CORE_REVOCATION_EXPORT','CORE_DATABASE_EXPORT'):Path(kwargs['env'][key]).write_bytes(b'synthetic backup')
        ordinary=deploy.write_private
        def write(path,data):
            self.assertTrue(self.held);self.events.append(('journal',None));ordinary(path,data)
        with patch.object(deploy,'require_host'),patch.object(deploy,'stop_core_writers',return_value=cleanup),patch.object(deploy,'skill_writer_lock',side_effect=self.fence),patch.object(deploy,'NGINX',str(nginx)),patch.object(deploy,'verify_release',return_value=self.root/'release'),patch.object(deploy,'load_environment',return_value={}),patch.object(deploy,'command',side_effect=command),patch.object(deploy,'write_private',side_effect=write):
            result=deploy.maintenance(self.args)
        self.assertTrue(result['writers_stopped']);self.assertTrue(result['safety_cleanup']['skill_writers_quiescent'])
        self.assertEqual(self.events[0][1],{'exclusive':True});self.assertFalse(self.held)
        self.assertLess(self.events.index(('backup',None)),self.events.index(('journal',None)))
        self.assertLess(self.events.index(('journal',None)),self.events.index(('unlock',None)))

    def test_busy_maintenance_retains_gate_and_never_exports_moving_ledger(self):
        self.gate.touch();cleanup={'cleanup_complete':True,'writers_stopped':True,'errors':[]}
        with patch.object(deploy,'require_host'),patch.object(deploy,'stop_core_writers',return_value=cleanup),patch.object(deploy,'skill_writer_lock',side_effect=TimeoutError('synthetic busy')),patch.object(deploy,'verify_release') as verify,patch.object(deploy,'load_environment') as env,patch.object(deploy,'command') as command:
            with self.assertRaises(TimeoutError):deploy.maintenance(self.args)
            verify.assert_not_called();env.assert_not_called();command.assert_not_called()
        self.assertTrue(self.gate.exists());self.assertFalse(cleanup['writers_stopped']);self.assertFalse(cleanup['cleanup_complete'])
        self.assertFalse(cleanup['skill_writers_quiescent']);self.assertEqual(cleanup['errors'][0]['code'],'CORE_SKILL_WRITER_FENCE_BUSY')

    def test_first_freeze_retires_skill_before_hermes_refresh_and_final_snapshot(self):
        source=self.root/'legacy';source.mkdir();(source/'original.txt').write_text('old original')
        with closing(sqlite3.connect(source/'web.db')) as connection,connection:connection.execute('CREATE TABLE originals(value TEXT)');connection.execute("INSERT INTO originals VALUES('preserved')")
        hermes=self.root/'hermes.db'
        with closing(sqlite3.connect(hermes)) as connection,connection:connection.execute('CREATE TABLE originals(value TEXT)')
        skill=self.root/'skills/zhiming';skill.mkdir(parents=True);old=b'# original synthetic Python bytes\n';(skill/'archive.py').write_bytes(old);(skill/'SKILL.md').write_bytes(b'old instructions')
        fixed=self.root/'releases'/SHA;(fixed/'hermes').mkdir(parents=True);(fixed/'hermes/SKILL.md').write_bytes(b'new skill')
        files={'hermes/SKILL.md':{'sha256':hashlib.sha256(b'new skill').hexdigest()}}
        (fixed/deploy.MANIFEST).write_text(json.dumps({'schema':'core3-release-v1','commit':SHA,'files':files}))
        self.args.release_dir=fixed.as_posix()
        config=self.root/'config.yaml';config.write_text('platforms:\n  feishu:\n    enabled: true\n  telegram:\n    enabled: true\n')
        jobs=self.root/'jobs.json';jobs.write_text(json.dumps([{'id':str(i),'prompt':'zhiming/report_pipeline.py','enabled':True} for i in range(4)]+[{'id':'other','prompt':'another app','enabled':True}]))
        ids=self.root/'ids.json';ids.write_text(json.dumps(['0','1','2','3']));self.args.legacy_job_ids=str(ids)
        nginx=self.root/'nginx';nginx.write_text(NGINX);copied=[];ordinary_copy=deploy.shutil.copytree
        def command(argv,**kwargs):
            if argv[0]=='nginx' or argv==['systemctl','reload','nginx']:
                self.assertTrue(self.gate.exists());return
            self.assertTrue(self.held)
            if '--property=KillMode' in argv:return 'control-group'
            if '--property=SendSIGKILL' in argv:return 'yes'
            if argv==['systemctl','restart','hermes.service']:
                self.assertEqual((skill/'archive.py').read_bytes(),deploy.retired_skill_stub());self.assertTrue(self.gate.exists());self.events.append(('refresh',None))
            self.assertNotEqual(argv,['systemctl','stop','hermes.service'])
        def copy(src,dst,**kwargs):
            self.assertTrue(self.held);self.assertIn(('refresh',None),self.events);self.assertTrue(kwargs['dirs_exist_ok']);copied.append(True)
            return ordinary_copy(src,dst,**kwargs)
        with ExitStack() as stack:
            for name,value in {'RELEASE_ROOT':(self.root/'releases').as_posix(),'LEGACY_SOURCE':str(source),'LEGACY_HERMES_DB':str(hermes),'LEGACY_CONFIG':str(config),'LEGACY_JOBS':str(jobs),'HERMES_SKILL':str(skill),'NGINX':str(nginx)}.items():stack.enter_context(patch.object(deploy,name,value))
            stack.enter_context(patch.object(deploy,'require_host'));stack.enter_context(patch.object(deploy,'evidence',return_value={}))
            stack.enter_context(patch.object(deploy,'skill_writer_lock',side_effect=self.fence));stack.enter_context(patch.object(deploy,'command',side_effect=command));stack.enter_context(patch.object(deploy.shutil,'copytree',side_effect=copy))
            result=deploy.freeze(self.args)
            backup=Path(result['source_snapshot']).parent/'hermes-skill';before={p.name:p.read_bytes() for p in backup.iterdir()}
            deploy.install_hermes_skill(self.args,Path(result['source_snapshot']))
            self.assertEqual(before,{p.name:p.read_bytes() for p in backup.iterdir()});self.assertEqual((backup/'archive.py').read_bytes(),old)
        self.assertTrue(copied);self.assertTrue(result['skill_writers_quiescent']);self.assertTrue(result['skill_entrypoints_retired_before_snapshot'])
        with closing(sqlite3.connect(Path(result['source_snapshot'])/'web.db')) as connection:self.assertEqual(connection.execute('SELECT value FROM originals').fetchone()[0],'preserved')
        self.assertEqual(json.loads(jobs.read_text())[-1]['enabled'],True)

    def test_stopped_units_do_not_claim_complete_while_skill_cli_is_busy(self):
        def command(argv,**kwargs):
            return 'inactive' if '--property=ActiveState' in argv else 'disabled' if '--property=UnitFileState' in argv else None
        with patch.object(deploy,'command',side_effect=command),patch.object(deploy,'skill_writer_lock',side_effect=TimeoutError('synthetic busy')):
            result=deploy.stop_core_writers()
        self.assertTrue(self.gate.exists());self.assertTrue(result['unit_writers_stopped'])
        self.assertFalse(result['skill_writers_quiescent']);self.assertFalse(result['writers_stopped']);self.assertFalse(result['cleanup_complete'])

    def test_initial_freeze_refuses_restart_that_can_leave_old_children_alive(self):
        config=self.root/'config.yaml';config.write_text('platforms:\n  feishu:\n    enabled: true\n')
        jobs=self.root/'jobs.json';jobs.write_text(json.dumps([{'id':str(i),'prompt':'zhiming/report_pipeline.py','enabled':True} for i in range(4)]))
        ids=self.root/'ids.json';ids.write_text(json.dumps(['0','1','2','3']));self.args.legacy_job_ids=str(ids)
        nginx=self.root/'nginx';nginx.write_text(NGINX)
        for mode,kill in [('process','yes'),('control-group','no')]:
            with self.subTest(mode=mode,send_sigkill=kill),ExitStack() as stack:
                for name,value in {'LEGACY_CONFIG':str(config),'LEGACY_JOBS':str(jobs),'NGINX':str(nginx)}.items():stack.enter_context(patch.object(deploy,name,value))
                stack.enter_context(patch.object(deploy,'stamp',return_value='case-'+mode+kill))
                stack.enter_context(patch.object(deploy,'require_host'));stack.enter_context(patch.object(deploy,'verify_release',return_value=self.root/'release'));stack.enter_context(patch.object(deploy,'evidence',return_value={}))
                stack.enter_context(patch.object(deploy,'skill_writer_lock',side_effect=self.fence))
                stack.enter_context(patch.object(deploy,'command',side_effect=lambda argv,**kwargs:mode if '--property=KillMode' in argv else kill if '--property=SendSIGKILL' in argv else None))
                install=stack.enter_context(patch.object(deploy,'install_hermes_skill'));snapshot=stack.enter_context(patch.object(deploy,'snapshot_sqlite'))
                with self.assertRaisesRegex(ValueError,'terminate old skill children'):deploy.freeze(self.args)
                install.assert_not_called();snapshot.assert_not_called();self.assertTrue(self.gate.exists())

    def test_withdrawal_restore_busy_fence_never_reads_env_or_starts_pg_apply(self):
        self.gate.touch();self.args.withdrawals=str(self.root/'unread.json')
        with patch.object(deploy,'require_host'),patch.object(deploy,'verify_release',return_value=self.root/'release'),patch.object(deploy,'verify_legacy_disabled'),patch.object(deploy.subprocess,'run',return_value=Namespace(returncode=3)),patch.object(deploy,'skill_writer_lock',side_effect=TimeoutError('synthetic busy')),patch.object(deploy,'load_environment') as env,patch.object(deploy,'command') as command:
            with self.assertRaises(TimeoutError):deploy.restore_withdrawals(self.args)
            env.assert_not_called();command.assert_not_called()
        self.assertTrue(self.gate.exists())

    def test_withdrawal_restore_holds_fence_through_apply_and_receipt(self):
        self.gate.touch();directory=self.root/'backups/latest';directory.mkdir(parents=True)
        path=directory/'withdrawals-latest.json';path.write_text('{}');path.chmod(0o600)
        (directory/'maintenance.json').write_text(json.dumps({'withdrawals':path.name,'withdrawals_sha256':deploy.file_sha(path),'database':deploy.DBS['live']}))
        self.args.withdrawals=str(path);self.args.migration_env_file=['/protected/migrate.env']
        ordinary_stat=Path.stat
        def protected_stat(target,*args,**kwargs):
            if target==path:return Namespace(st_mode=0o100600)
            return ordinary_stat(target,*args,**kwargs)
        def environment(args,db):
            self.assertTrue(self.held);self.assertEqual(args.env_file,['/protected/migrate.env']);return {}
        def apply(argv,**kwargs):
            self.assertTrue(self.held);self.events.append(('apply',None));return '{"withdrawals":2}'
        with patch.object(deploy,'require_host'),patch.object(deploy,'verify_release',return_value=self.root/'release'),patch.object(deploy,'verify_legacy_disabled'),patch.object(deploy.subprocess,'run',return_value=Namespace(returncode=3)),patch.object(deploy,'skill_writer_lock',side_effect=self.fence),patch.object(Path,'stat',protected_stat),patch.object(deploy,'load_environment',side_effect=environment),patch.object(deploy,'command',side_effect=apply):
            result=deploy.restore_withdrawals(self.args)
        self.assertEqual(result['withdrawals'],2);self.assertTrue(result['withdrawals_replayed']);self.assertTrue(self.gate.exists());self.assertFalse(self.held)
        self.assertEqual(self.events[0][1],{'exclusive':True});self.assertLess(self.events.index(('apply',None)),self.events.index(('unlock',None)))


if __name__=='__main__':unittest.main()
