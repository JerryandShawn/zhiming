"""Bound run evidence is checked with the real validator, without a provider."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'hermes'))
from state_store import StateStore,RevisionConflict
from context_query import ChannelContext
from guidance import normalize_final

class BoundEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.state=StateStore(self.temp.name);self.state.ensure_owner('alice')
        self.state.bind_channel('alice','report','report-alice')
        row=self.state.import_message('alice','web','source:user','user','我喜欢简洁的回答')
        self.fact=self.state.put_fact('alice','self',row['content'],[{'message_id':row['id'],'quote':row['content']}],kind='preference')
        self.bridge=ChannelContext(self.temp.name)
    def test_bound_fact_ref_is_reauthorized_and_coarse_archive_ref_rejected(self):
        run=self.bridge.prepare('我的偏好是什么','report','report-alice')
        doc=normalize_final({'plain_summary':'你偏好简洁的回答。','evidence':[{'ref':'fact:'+self.fact['id'],'claim':'用户原话记录的偏好'}]})
        result=self.bridge.validate_response(doc,'report','report-alice',run['run_id'],[],message='我的偏好是什么')
        self.assertTrue(result['validated']);self.assertIn('简洁',result['content'])
        bad=normalize_final({'plain_summary':'从旧档案读取。','evidence':[{'ref':'archive:user','claim':'整个旧档案'}]})
        with self.assertRaises(ValueError):self.bridge.validate_response(bad,'report','report-alice',run['run_id'],[],message='我的偏好是什么')
    def test_retrieved_original_ref_has_live_owner_and_revision_gate(self):
        row=self.state.import_message('alice','web','original:user','user','课程有十节，每节两小时')
        run=self.bridge.prepare('课程有几节','report','report-alice')
        ref='source:'+row['id'];self.assertIn(ref,run['evidence'])
        doc=normalize_final({'plain_summary':'课程有十节。','evidence':[{'ref':ref,'claim':'用户陈述的课程安排'}]})
        self.assertTrue(self.bridge.validate_response(doc,'report','report-alice',run['run_id'],[],message='课程有几节')['validated'])
        self.state.import_message('alice','web','correction:user','user','刚才课程安排有变化')
        with self.assertRaises(RevisionConflict):self.bridge.validate_response(doc,'report','report-alice',run['run_id'],[],message='课程有几节')

if __name__=='__main__':unittest.main()
