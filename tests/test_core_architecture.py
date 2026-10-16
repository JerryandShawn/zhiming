"""Static boundaries supplement, but never substitute for runtime regressions."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def imported_names(path):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    names=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import): names.extend(alias.name for alias in node.names)
        if isinstance(node,ast.ImportFrom): names.append(node.module or '')
    return names


class CoreArchitectureTests(unittest.TestCase):
    def test_pure_domain_imports_no_runtime_provider_web_or_database(self):
        for path in (ROOT/'mingjing_core/domain').glob('*.py'):
            with self.subTest(path=path.name):
                self.assertFalse(any(name.split('.')[0] in ('fastapi','langgraph','openai','psycopg','sqlite3','httpx') for name in imported_names(path)))

    def test_runtime_state_contract_contains_only_identifiers_and_phase(self):
        path=ROOT/'mingjing_core/runtime/graph.py'
        tree=ast.parse(path.read_text(encoding='utf-8'))
        state=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='RunState')
        fields={node.target.id for node in state.body if isinstance(node,ast.AnnAssign)}
        self.assertEqual(fields,{'owner','run_id','phase'})

    def test_core_business_paths_and_calculators_do_not_import_legacy_agent(self):
        paths=list((ROOT/'mingjing_core').rglob('*.py'))+[ROOT/'hermes'/f'{name}.py' for name in ('bazi','ziwei','astro')]
        for path in paths:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertFalse(any(name=='hermes.agent' or name.startswith('hermes.agent.') or name=='agent' for name in imported_names(path)))

    def test_postgres_authority_has_no_sqlite_fallback(self):
        self.assertNotIn('sqlite3',imported_names(ROOT/'mingjing_core/repositories/postgres.py'))

    def test_web_and_channel_adapters_share_business_service(self):
        for relative in ('adapters/web.py','adapters/channels/hermes.py','adapters/channels/reports.py'):
            path=ROOT/'mingjing_core'/relative
            self.assertTrue(any(name.endswith('application.consultation') for name in imported_names(path)),relative)
        self.assertFalse(any('adapters.model' in name for name in imported_names(ROOT/'mingjing_core/adapters/web.py')))


    def test_exact_102_legacy_ids_map_to_defined_current_scenarios(self):
        manifest=json.loads((ROOT/'docs/CORE_V3_BEHAVIOR_COVERAGE.json').read_text(encoding='utf-8'))
        actual=set()
        for source in manifest['legacy_baseline']['source_files']:
            path=ROOT/source['file'];self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),source['sha256'])
            for c in ast.parse(path.read_text(encoding='utf-8')).body:
                if isinstance(c,ast.ClassDef):
                    actual.update(path.stem+'.'+c.name+'.'+f.name for f in c.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef)) and f.name.startswith('test_'))
        self.assertEqual(len(actual),102);self.assertEqual(actual,{e['legacy_id'] for e in manifest['entries']})
        for entry in manifest['entries']:
            self.assertIn(entry['status'],('covered','intentional_change'));self.assertTrue(entry['scope_and_change'])
            self.assertTrue(entry['new_scenarios'])
            for scenario in entry['new_scenarios']:
                path=ROOT/scenario['file'];ids=set()
                for c in ast.parse(path.read_text(encoding='utf-8')).body:
                    if isinstance(c,ast.ClassDef):
                        ids.update(path.stem+'.'+c.name+'.'+f.name for f in c.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef)) and f.name.startswith('test_'))
                self.assertIn(scenario['test_id'],ids)


if __name__=='__main__': unittest.main()
