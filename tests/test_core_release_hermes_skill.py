"""Hermes retirement uses real temporary files, no model or external process service."""
from argparse import Namespace
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import deploy_core as release

SHA='b'*40


class ExecCaptured(BaseException):
    pass


class CoreHermesSkillRetirement(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.fixed=self.root/'releases'/SHA;(self.fixed/'hermes').mkdir(parents=True)
        (self.fixed/'hermes/SKILL.md').write_bytes(b'fixed Core skill: only core_consultation.py\n')
        (self.fixed/'hermes/core_consultation.py').write_bytes(b'# fixed Core CLI fixture\n')
        files={str(p.relative_to(self.fixed)).replace('\\','/'):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in self.fixed.rglob('*') if p.is_file()}
        (self.fixed/release.MANIFEST).write_text(json.dumps({'schema':'core3-release-v1','commit':SHA,'files':files}))
        self.skill=self.root/'skills/zhiming';self.skill.mkdir(parents=True)
        self.old={'SKILL.md':b'old instructions', 'archive.py':b'raise RuntimeError("old archive should never execute")\n', 'context_query.py':b'# old query\n', 'custom_legacy.py':b'# known original extra CLI\n'}
        for name,data in self.old.items():(self.skill/name).write_bytes(data)
        (self.skill/'archive.json').write_bytes(b'{"private":"must remain unchanged"}')
        (self.skill/'web.db').write_bytes(b'private original database remains byte-identical')
        self.source=self.root/'backups/frozen/source';self.source.mkdir(parents=True)
        self.env1=self.root/'web.env';self.env2=self.root/'hermes.env';self.env3=self.root/'live.env'
        self.env1.write_text('SYNTHETIC_TEST_SECRET="fictional value"\nSETTING=web\n')
        self.env2.write_text('SETTING=hermes\n')
        self.env3.write_text('SETTING=core\nZHIMING_DATABASE_URL=postgresql://synthetic:fixture@127.0.0.1/zhiming_core_live\nCHART_PYTHON='+json.dumps(str(self.fixed/'venv/charts/bin/python'))+'\n')
        self.args=Namespace(commit=SHA,release_dir=self.fixed.as_posix(),env_file=[str(p) for p in (self.env1,self.env2,self.env3)])
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.addCleanup(self.temporary.cleanup)
        for name,value in {'RELEASE_ROOT':(self.root/'releases').as_posix(),'BACKUP_ROOT':str(self.root/'backups'),'HERMES_SKILL':str(self.skill)}.items():self.stack.enter_context(patch.object(release,name,value))

    def test_real_install_retires_old_python_and_preserves_private_files_and_originals(self):
        originals={name:(self.skill/name).read_bytes() for name in ('archive.json','web.db')}
        result=release.install_hermes_skill(self.args,self.source)
        self.assertTrue(result['installed']);self.assertEqual(result['model_calls'],0);self.assertEqual(result['external_sends'],0)
        backup=self.source.parent/'hermes-skill'
        for name,data in self.old.items():self.assertEqual((backup/name).read_bytes(),data)
        for name,data in originals.items():self.assertEqual((self.skill/name).read_bytes(),data)
        self.assertEqual((self.skill/'SKILL.md').read_bytes(),(self.fixed/'hermes/SKILL.md').read_bytes())
        self.assertTrue(release.verify_hermes_skill(self.args)['verified'])
        for name in ('archive.py','context_query.py','custom_legacy.py','chat_agent.py','report_pipeline.py'):
            process=subprocess.run([sys.executable,str(self.skill/name),'merge','--json','fictional-old-argv'],capture_output=True)
            self.assertEqual(process.returncode,64);self.assertIn(b'LEGACY_SKILL_RETIRED',process.stderr)
            self.assertEqual(process.stdout,b'')
        installed=json.loads((self.skill/release.SKILL_MANIFEST).read_text())
        self.assertEqual(set(installed['original_files']),set(self.old))

    def test_replay_never_overwrites_original_backup_and_tamper_blocks(self):
        release.install_hermes_skill(self.args,self.source)
        backup=self.source.parent/'hermes-skill';before={p.name:p.read_bytes() for p in backup.iterdir()}
        release.install_hermes_skill(self.args,self.source)
        self.assertEqual({p.name:p.read_bytes() for p in backup.iterdir()},before)
        (backup/'archive.py').write_bytes(b'changed original backup')
        with self.assertRaisesRegex(ValueError,'backup changed'):release.install_hermes_skill(self.args,self.source)
        self.assertEqual((backup/'archive.py').read_bytes(),b'changed original backup')

    def test_wrapper_reads_actual_env_order_and_execs_exact_python_cli_argv(self):
        release.install_hermes_skill(self.args,self.source)
        argv=['core_consultation.py','--channel','fictional','consult','--message-id','fictional;$(do_not_execute)']
        ordinary_stat=Path.stat
        def protected_stat(path,*args,**kwargs):
            if path in (self.env1,self.env2,self.env3):return Namespace(st_mode=0o100600)
            return ordinary_stat(path,*args,**kwargs)
        captured={}
        def capture(binary,args):
            captured.update(binary=binary,args=args,setting=os.environ['SETTING'],secret=os.environ['SYNTHETIC_TEST_SECRET'],pool=os.environ['CORE_DB_POOL_SIZE'])
            raise ExecCaptured()
        with patch.object(Path,'stat',protected_stat),patch.object(sys,'argv',argv),patch.object(sys,'path',list(sys.path)),patch.dict(os.environ,{},clear=True),patch.object(os,'execv',side_effect=capture):
            with self.assertRaises(ExecCaptured):runpy.run_path(str(self.skill/'core_consultation.py'),run_name='__main__')
        expected=str(self.fixed/'venv/core/bin/python')
        self.assertEqual(captured['binary'],expected)
        self.assertEqual(captured['args'],[expected,str(self.fixed/'hermes/core_consultation.py'),*argv[1:]])
        self.assertEqual(captured['setting'],'core');self.assertEqual(captured['secret'],'fictional value');self.assertEqual(captured['pool'],'4')
        text=(self.skill/'core_consultation.py').read_text()
        self.assertNotIn('fictional value',text);self.assertNotIn('postgresql://',text)

    def test_wrapper_does_not_exec_with_unprotected_env_or_modified_release(self):
        release.install_hermes_skill(self.args,self.source)
        for modified in (False,True):
            if modified:(self.fixed/'hermes/SKILL.md').write_bytes(b'modified fixed source')
            with patch.object(sys,'argv',['core_consultation.py','consult']),patch.object(sys,'path',list(sys.path)),patch.object(os,'execv') as execute:
                with self.assertRaises(SystemExit) as rejected:runpy.run_path(str(self.skill/'core_consultation.py'),run_name='__main__')
                self.assertEqual(rejected.exception.code,78);execute.assert_not_called()

    def test_publish_verification_blocks_unknown_entrypoint_and_changed_stub_or_wrapper(self):
        release.install_hermes_skill(self.args,self.source)
        (self.skill/'new_side_effect.py').write_text('raise RuntimeError("unknown")')
        with self.assertRaisesRegex(ValueError,'Unknown or missing'):release.verify_hermes_skill(self.args)
        with self.assertRaisesRegex(ValueError,'Unknown Hermes Python'):release.install_hermes_skill(self.args,self.source)
        (self.skill/'new_side_effect.py').unlink()
        for name in ('archive.py','core_consultation.py','SKILL.md'):
            original=(self.skill/name).read_bytes();(self.skill/name).write_bytes(original+b'\n# modified\n')
            with self.assertRaisesRegex(ValueError,'changed'):release.verify_hermes_skill(self.args)
            (self.skill/name).write_bytes(original)
        changed=Namespace(**vars(self.args));changed.env_file=list(reversed(self.args.env_file))
        with self.assertRaisesRegex(ValueError,'environment order'):release.verify_hermes_skill(changed)

    def test_path_constraints_reject_outside_snapshot_and_non_directory_member(self):
        outside=self.root/'untrusted/source';outside.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'frozen source'):release.install_hermes_skill(self.args,outside)
        (self.skill/'directory.py').mkdir()
        with self.assertRaisesRegex(ValueError,'ordinary file'):release.install_hermes_skill(self.args,self.source)
        with patch.object(release,'HERMES_SKILL',str(self.root/'skills/other')):
            with self.assertRaisesRegex(ValueError,'explicit'):release.install_hermes_skill(self.args,self.source)


if __name__=='__main__':unittest.main()
