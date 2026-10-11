"""Release safety checks use temporary files; no host or external side effects."""
from argparse import Namespace
from contextlib import ExitStack,closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import yaml

from tools import deploy_core as release

SHA='a'*40
NGINX='''server {
    listen 80;
    location / {
        return 301 https://$host$request_uri;
    }
}
server {
    listen 443 ssl;
    server_name p.jerrymeng.asia;
    location / {
        proxy_pass http://127.0.0.1:8787;
    }
}
'''


class CoreReleaseTool(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.args=Namespace(commit=SHA,release_dir=release.RELEASE_ROOT+'/'+SHA,env_file=['/etc/systemd/system/mingjingtai.env','/root/core-live.env'])

    def tearDown(self):self.temporary.cleanup()

    def artifact(self,rows):
        path=self.root/'release.tar.gz'
        with tarfile.open(path,'w:gz') as archive:
            for name,data in rows.items():
                info=tarfile.TarInfo(name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
        return path,hashlib.sha256(path.read_bytes()).hexdigest()

    def test_release_is_pinned_and_archive_names_cannot_escape(self):
        release.release_path(SHA,self.args.release_dir)
        for commit,path in [('main',self.args.release_dir),(SHA,release.RELEASE_ROOT+'/current'),(SHA,release.RELEASE_ROOT+'/'+SHA+'/../other')]:
            with self.assertRaises(ValueError):release.release_path(commit,path)
        for name in ('../secret','/etc/passwd','a/../../b','a\\b','.'):
            with self.assertRaises(ValueError):release.safe_member(name)

    def test_artifact_requires_reviewed_digest_exact_manifest_and_members(self):
        content=b'fixed release bytes'
        manifest={'schema':'core3-release-v1','commit':SHA,'files':{'app.py':{'sha256':release.sha(content),'mode':0o644}}}
        rows={release.MANIFEST:json.dumps(manifest).encode(),'app.py':content}
        path,digest=self.artifact(rows)
        self.assertEqual(release.verify_artifact(path,digest,SHA),manifest)
        with self.assertRaises(ValueError):release.verify_artifact(path,'0'*64,SHA)
        with self.assertRaises(ValueError):release.verify_artifact(path,digest,'b'*40)
        rows['app.py']=b'changed bytes';path,digest=self.artifact(rows)
        with self.assertRaises(ValueError):release.verify_artifact(path,digest,SHA)
        rows['../secret']=b'escape';path,digest=self.artifact(rows)
        with self.assertRaises(ValueError):release.verify_artifact(path,digest,SHA)

    def test_bundle_uses_committed_lf_blobs_instead_of_working_crlf(self):
        source=self.root/'checkout';source.mkdir()
        def git(*args):return subprocess.run(['git',*args],cwd=source,check=True,capture_output=True).stdout.decode().strip()
        git('init');git('config','core.autocrlf','false')
        (source/'.gitattributes').write_bytes(b'*.py text\n')
        (source/'app.py').write_bytes(b'print("fixture")\r\n')
        git('add','.');git('-c','user.name=Local Fixture','-c','user.email=fixture@example.invalid','commit','-m','canonical local fixture')
        commit=git('rev-parse','HEAD');artifact=self.root/'bundle.tar.gz'
        args=Namespace(source=str(source),commit=commit,artifact=str(artifact))
        result=release.bundle(args);manifest=release.verify_artifact(artifact,result['sha256'],commit)
        canonical=b'print("fixture")\n'
        self.assertEqual(manifest['files']['app.py']['sha256'],release.sha(canonical))
        self.assertEqual(manifest['files']['app.py']['git_blob_sha1'],git('rev-parse',commit+':app.py'))
        with tarfile.open(artifact,'r:gz') as archive:self.assertEqual(archive.extractfile('app.py').read(),canonical)
        (source/'app.py').write_bytes(b'dirty source\n')
        with self.assertRaises(ValueError):release.bundle(args)

    def test_nginx_gate_preserves_redirect_proxy_and_supports_sse(self):
        result=release.render_nginx(NGINX)
        self.assertEqual(release.render_nginx(result),result)
        self.assertIn('return 301 https://$host$request_uri;',result)
        self.assertIn('proxy_pass http://127.0.0.1:8787;',result)
        self.assertIn('if (-f '+release.MAINTENANCE+') { return 503; }',result)
        self.assertIn('internal;',result);self.assertIn('proxy_buffering off;',result)
        http,https=result.split('server {',2)[1:]
        self.assertNotIn('core-maintenance',http);self.assertIn('return 301',http)
        self.assertIn('core-maintenance',https);self.assertIn('proxy_pass http://127.0.0.1:8787;',https)
        with self.assertRaises(ValueError):release.render_nginx(NGINX+'server {}\n')
        with self.assertRaises(ValueError):release.render_nginx(NGINX.replace('proxy_pass','proxy_buffering on; proxy_pass'))
        misplaced=NGINX.replace('return 301 https://$host$request_uri;','# Core v3 maintenance gate\n        if (-f '+release.MAINTENANCE+') { return 503; }\n        error_page 503 =503 /core-maintenance.html;')
        with self.assertRaises(ValueError):release.render_nginx(misplaced)

    def test_units_have_one_web_worker_separate_calculator_and_single_effect_entries(self):
        units=release.units(self.args)
        self.assertIn('--workers 1',units['mingjingtai.service'])
        self.assertIn('CORE_DB_POOL_SIZE=4',units['mingjingtai.service'])
        self.assertIn(self.args.release_dir+'/venv/charts/bin/python',units['mingjingtai.service'])
        self.assertIn('EnvironmentFile=/etc/systemd/system/mingjingtai.env',units['mingjingtai.service'])
        self.assertIn('mingjing_core.adapters.feishu_gateway',units['zhiming-core-feishu.service'])
        self.assertIn('CORE_FEISHU_ENABLED=true',units['zhiming-core-feishu.service'])
        self.assertIn('core_report_worker --owner primary',units['zhiming-core-reports.service'])
        self.assertIn('Asia/Shanghai',units['zhiming-core-reports.timer'])
        self.assertTrue(all('ChatAgent' not in text and 'report_pipeline.py' not in text for text in units.values()))

    def test_environment_literals_preserve_tokens_json_and_do_not_expand(self):
        result=release.parse_environment('MINGJING_TOKEN=synthetic-token\nZHIMING_TOKEN_OWNERS={"token":"owner"}\nKIMI_API_KEY=\'${LITERAL} # value\'\nEMPTY=\n')
        self.assertEqual(result['ZHIMING_TOKEN_OWNERS'],'{"token":"owner"}')
        self.assertEqual(result['KIMI_API_KEY'],'${LITERAL} # value')
        self.assertEqual(result['EMPTY'],'')
        for bad in ('export TOKEN=value','A=two bare words','invalid-name=x'):
            with self.assertRaises(ValueError):release.parse_environment(bad)

    def test_acceptance_cannot_substitute_a_different_commit_or_skipped_calculators(self):
        path=self.root/'acceptance.json';self.args.acceptance=str(path)
        row={'commit':SHA,'database':'zhiming_core_stage','calculator_skips':0,'stage_accepted':True,'frontend_passed':True,'migration_replay_passed':True,'live_provider_smoke_passed':True}
        path.write_text(json.dumps(row));self.assertEqual(release.evidence(self.args),row)
        for change in ({'commit':'b'*40},{'calculator_skips':1},{'database':'zhiming_core_live'},{'live_provider_smoke_passed':False}):
            path.write_text(json.dumps(dict(row,**change)))
            with self.assertRaises(ValueError):release.evidence(self.args)

    def test_legacy_cron_selection_is_exactly_four_known_jobs(self):
        jobs=[{'id':str(i),'prompt':'zhiming/report_pipeline.py','enabled':True} for i in range(4)]+[{'id':'unrelated','prompt':'another app','enabled':True}]
        path=self.root/'ids.json';path.write_text(json.dumps(['0','1','2','3']))
        selected,found=release.legacy_jobs(path,jobs)
        self.assertEqual(selected,['0','1','2','3']);self.assertEqual(len(found),4)
        path.write_text(json.dumps(['0','1','2','unrelated']))
        with self.assertRaises(ValueError):release.legacy_jobs(path,jobs)
        path.write_text(json.dumps([str(i) for i in range(8)]))
        with self.assertRaises(ValueError):release.legacy_jobs(path,jobs)

    def test_freeze_copies_both_sqlite_databases_and_preserves_other_channels_jobs(self):
        source=self.root/'legacy';source.mkdir()
        for name,value in [('web.db','web-original'),('reports.db','report-original')]:
            with closing(sqlite3.connect(source/name)) as connection,connection:
                connection.execute('CREATE TABLE originals(value TEXT)');connection.execute('INSERT INTO originals VALUES(?)',(value,))
        hermes=self.root/'state.db'
        with closing(sqlite3.connect(hermes)) as connection,connection:
            connection.execute('CREATE TABLE originals(value TEXT)');connection.execute("INSERT INTO originals VALUES('hermes-original')")
        config=self.root/'hermes.yaml';config.write_text(yaml.safe_dump({'platforms':{'feishu':{'enabled':True},'telegram':{'enabled':True}},'custom':{'kept':123}}))
        jobs=self.root/'jobs.json';jobs.write_text(json.dumps([{'id':str(i),'prompt':'zhiming/report_pipeline.py','enabled':True} for i in range(4)]+[{'id':'other','prompt':'unrelated','enabled':True}]))
        ids=self.root/'ids.json';ids.write_text(json.dumps(['0','1','2','3']));self.args.legacy_job_ids=str(ids)
        nginx=self.root/'nginx.conf';nginx.write_text(NGINX)
        commands=[]
        with ExitStack() as stack:
            for name,value in {'BACKUP_ROOT':str(self.root/'backups'),'LEGACY_SOURCE':str(source),'LEGACY_HERMES_DB':str(hermes),'LEGACY_CONFIG':str(config),'LEGACY_JOBS':str(jobs),'NGINX':str(nginx),'MAINTENANCE':str(self.root/'gate'),'MAINTENANCE_HTML':str(self.root/'maintenance.html')}.items():stack.enter_context(patch.object(release,name,value))
            stack.enter_context(patch.object(release,'require_host'))
            stack.enter_context(patch.object(release,'verify_release',return_value=self.root/'release'))
            stack.enter_context(patch.object(release,'evidence',return_value={}))
            stack.enter_context(patch.object(release,'command',side_effect=lambda argv,**kwargs:commands.append(argv)))
            journal=release.freeze(self.args)
        copied=Path(journal['source_snapshot'])
        for name,value in [('web.db','web-original'),('reports.db','report-original')]:
            with closing(sqlite3.connect(copied/name)) as connection:self.assertEqual(connection.execute('SELECT value FROM originals').fetchone()[0],value)
        self.assertEqual(release.snapshot_hashes(copied),journal['source_hashes'])
        frozen_hermes=Path(journal['hermes_snapshot'])
        self.assertEqual(release.file_sha(frozen_hermes),journal['hermes_sha256'])
        with closing(sqlite3.connect(frozen_hermes)) as connection:self.assertEqual(connection.execute('SELECT value FROM originals').fetchone()[0],'hermes-original')
        updated=yaml.safe_load(config.read_text());self.assertIs(updated['platforms']['feishu']['enabled'],False)
        self.assertIs(updated['platforms']['telegram']['enabled'],True);self.assertEqual(updated['custom'],{'kept':123})
        updated=json.loads(jobs.read_text());self.assertTrue(all(row['enabled'] is False for row in updated[:4]));self.assertIs(updated[4]['enabled'],True)
        self.assertIn(['systemctl','restart','hermes.service'],commands)
        self.assertIn(['systemctl','stop','mingjingtai.service'],commands)
        self.assertNotIn(['systemctl','stop','hermes.service'],commands)

    def test_maintenance_stops_writers_before_a_modified_release_can_block_export(self):
        nginx=self.root/'nginx.conf';nginx.write_text(NGINX);steps=[]
        with ExitStack() as stack:
            for name,value in {'NGINX':str(nginx),'MAINTENANCE':str(self.root/'gate'),'MAINTENANCE_HTML':str(self.root/'maintenance.html')}.items():stack.enter_context(patch.object(release,name,value))
            stack.enter_context(patch.object(release,'require_host'))
            stack.enter_context(patch.object(release,'command',side_effect=lambda argv,**kwargs:steps.append(argv)))
            def reject(_):
                self.assertTrue((self.root/'gate').is_file())
                self.assertIn(['systemctl','stop','mingjingtai.service'],steps)
                self.assertIn(['systemctl','stop','zhiming-core-feishu.service'],steps)
                raise ValueError('modified release')
            stack.enter_context(patch.object(release,'verify_release',side_effect=reject))
            with self.assertRaisesRegex(ValueError,'modified release'):release.maintenance(self.args)
        self.assertIn(['systemctl','reload','nginx'],steps)
        self.assertIn('Core v3 maintenance gate',nginx.read_text())

    def test_withdrawal_restore_is_refused_without_a_gate_or_with_active_writers(self):
        gate=self.root/'gate'
        with ExitStack() as stack:
            stack.enter_context(patch.object(release,'require_host'))
            stack.enter_context(patch.object(release,'verify_release',return_value=self.root/'release'))
            stack.enter_context(patch.object(release,'verify_legacy_disabled'))
            stack.enter_context(patch.object(release,'MAINTENANCE',str(gate)))
            run=stack.enter_context(patch.object(release.subprocess,'run',return_value=Namespace(returncode=0)))
            child=stack.enter_context(patch.object(release,'command'))
            with self.assertRaisesRegex(ValueError,'maintenance gate'):release.restore_withdrawals(self.args)
            run.assert_not_called();gate.touch()
            with self.assertRaisesRegex(ValueError,'writer stopped'):release.restore_withdrawals(self.args)
            child.assert_not_called()

    def test_install_imports_final_hermes_and_seeds_schedule_before_runtime_startup(self):
        import ast
        source=self.root/'backups/frozen/source';source.mkdir(parents=True)
        (source/'archive.json').write_text('{}')
        hermes=source.parent/'hermes-state.db';hermes.write_bytes(b'synthetic SQLite snapshot identity')
        bindings=self.root/'bindings.json';bindings.write_text('[]')
        frozen={'commit':SHA,'source_snapshot':str(source),'source_hashes':release.snapshot_hashes(source),'hermes_snapshot':str(hermes),'hermes_sha256':release.file_sha(hermes)}
        (source.parent/'freeze.json').write_text(json.dumps(frozen))
        self.args.source_snapshot=str(source);self.args.bindings=str(bindings);self.args.migration_env_file=['/protected/migrator.env']
        gate=self.root/'gate';gate.touch();commands=[];ordinary_stat=Path.stat
        def private_stat(path,*args,**kwargs):
            if path in (bindings,hermes):return Namespace(st_mode=0o100600)
            return ordinary_stat(path,*args,**kwargs)
        with ExitStack() as stack:
            stack.enter_context(patch.object(release,'require_host'))
            stack.enter_context(patch.object(release,'verify_release',return_value=self.root/'fixed-release'))
            stack.enter_context(patch.object(release,'evidence',return_value={}))
            stack.enter_context(patch.object(release,'verify_legacy_disabled'))
            stack.enter_context(patch.object(release,'BACKUP_ROOT',str(self.root/'backups')))
            stack.enter_context(patch.object(release,'MAINTENANCE',str(gate)))
            stack.enter_context(patch.object(Path,'stat',private_stat))
            stack.enter_context(patch.object(release,'load_environment',return_value={'ZHIMING_DATABASE_URL':'synthetic env-only DSN'}))
            stack.enter_context(patch.object(release,'units',return_value={}))
            stack.enter_context(patch.object(release,'command',side_effect=lambda argv,**kwargs:commands.append(argv)))
            result=release.install(self.args)
        self.assertTrue(result['maintenance']);self.assertFalse(result['effects_started'])
        children=[argv[2] for argv in commands if len(argv)>2 and argv[1]=='-c']
        for child in children:compile(child,'protected deployment child','exec')
        hermes_child=next(child for child in children if 'sync_frozen_hermes(repo,source,bindings)' in child)
        nodes=ast.parse(hermes_child)
        self.assertLess(hermes_child.index('sync_frozen_hermes(repo,source,bindings)'),hermes_child.index("seed_defaults('primary')"))
        joined='\n'.join(str(argv) for argv in commands)
        self.assertLess(joined.index('migration_core.py'),joined.index('sync_frozen_hermes(repo,source,bindings)'))
        self.assertLess(joined.index("seed_defaults('primary')"),joined.index('PostgresSaver(connection).setup()'))
        self.assertLess(joined.index('PostgresSaver(connection).setup()'),joined.index('ConsultationService.from_base()'))
        self.assertNotIn(['systemctl','enable','--now','zhiming-core-feishu.service'],commands)


if __name__=='__main__':unittest.main()
