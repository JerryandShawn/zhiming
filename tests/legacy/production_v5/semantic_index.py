"""Local multilingual dense vectors + lexical retrieval. No external data transfer."""
import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path

_lock=threading.RLock()
_encoder=None

class Encoder:
    def __init__(self,folder):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.folder=Path(folder)
        options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
        options.enable_cpu_mem_arena=False
        self.session=ort.InferenceSession(str(self.folder/'model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        self.tokenizer=Tokenizer.from_file(str(self.folder/'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding()
        self.inputs=[x.name for x in self.session.get_inputs()]

    def encode(self,texts):
        import numpy as np
        result=[]
        for start in range(0,len(texts),4):
            encoded=self.tokenizer.encode_batch(texts[start:start+4])
            values={'input_ids':np.array([x.ids for x in encoded],dtype=np.int64),
                    'attention_mask':np.array([x.attention_mask for x in encoded],dtype=np.int64),
                    'token_type_ids':np.array([x.type_ids for x in encoded],dtype=np.int64)}
            output=self.session.run(None,{k:values[k] for k in self.inputs})[0]
            mask=values['attention_mask'][...,None]
            vectors=(output*mask).sum(axis=1)/np.maximum(mask.sum(axis=1),1)
            vectors=vectors/np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-9)
            result.extend(vectors.astype(np.float32))
        return result

def encoder():
    global _encoder
    if _encoder is None:
        _encoder=Encoder(os.environ.get('ZHIMING_EMBEDDING_MODEL','/root/.hermes/zhiming/models/minilm'))
    return _encoder

def catalog(arc,history):
    from context_engine import dump
    docs=[]
    sections=['daily_log','forecast_registry','omen_dictionary','reports']
    sources={k:arc.get(k,[]) for k in sections}
    sources.update({'graph.'+k:v for k,v in arc.get('graph',{}).items() if isinstance(v,list)})
    sources['memory']=arc.get('conversation_state',{}).get('user_facts',[])
    for section,rows in sources.items():
        for i,item in enumerate(rows):
            if not isinstance(item,dict):continue
            if section=='memory' and item.get('status','active')!='active':continue
            ident=str(item.get('id') or item.get('date') or i)
            text=dump(item)
            for n,start in enumerate(range(0,len(text),180)):
                docs.append({'id':f'{section}:{ident}:{i}:{n}','source':section,'record_id':item.get('id',i),
                             'text':text[start:start+240],'date':str(item.get('date') or item.get('created_at') or ''),
                             'data':item if len(text)<=1800 else {'excerpt':text[start:start+1200],'id':item.get('id'),'date':item.get('date')}})
    for i,m in enumerate(history):
        if m.get('status') in ('running','failed','cancelled','interrupted'):continue
        text=str(m.get('content',''))
        ident=f"{m.get('source','web')}:{m.get('turn_id',m.get('id',i))}:{m.get('role')}"
        for n,start in enumerate(range(0,len(text),180)):
            docs.append({'id':f'history:{ident}:{n}','source':'history.'+m.get('source','web'),'record_id':m.get('turn_id',m.get('id',i)),
                         'text':text[start:start+240],'date':m.get('at',''),'data':{'role':m.get('role'),'at':m.get('at'),
                          'content':text[start:start+1200],'image_ids':m.get('image_ids',[]),'session_id':m.get('session_id')}})
    return docs

class SemanticIndex:
    def __init__(self,base):
        self.path=Path(base)/'retrieval.db'
        with sqlite3.connect(str(self.path)) as c:
            c.execute('PRAGMA journal_mode=DELETE')
            c.execute('CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,hash TEXT,body TEXT,vector BLOB)')
        self.status={'mode':'initializing','documents':0}

    def sync(self,docs):
        with _lock,sqlite3.connect(str(self.path),timeout=30) as c:
            existing=dict(c.execute('SELECT id,hash FROM documents'))
            changed=[]
            ids=set()
            for doc in docs:
                ids.add(doc['id']);digest=hashlib.sha256(json.dumps(doc,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                if existing.get(doc['id'])!=digest:changed.append((doc,digest))
            if changed:
                model=encoder()
                for start in range(0,len(changed),16):
                    batch=changed[start:start+16];vecs=model.encode([d['text'] for d,h in batch])
                    c.executemany('INSERT OR REPLACE INTO documents VALUES(?,?,?,?)',
                        [(d['id'],h,json.dumps(d,ensure_ascii=False),v.tobytes()) for (d,h),v in zip(batch,vecs)])
            removed=set(existing)-ids
            c.executemany('DELETE FROM documents WHERE id=?',[(ident,) for ident in removed])
            self.status={'mode':'hybrid','documents':len(ids),'updated':len(changed),'model':'multilingual-MiniLM-L12-v2-int8'}
        return self.status

    def search(self,query,limit=12,source=None):
        import numpy as np
        from context_engine import terms
        with _lock:
            qvec=encoder().encode([query])[0]
            with sqlite3.connect(str(self.path),timeout=15) as c:rows=c.execute('SELECT body,vector FROM documents').fetchall()
        query_terms=terms(query);matches=[]
        for body,vector in rows:
            doc=json.loads(body)
            if source and not doc['source'].startswith(source):continue
            cosine=float(np.dot(qvec,np.frombuffer(vector,dtype=np.float32)))
            overlap=len(query_terms & terms(doc['text']))/max(1,len(query_terms))
            score=.78*max(0,cosine)+.22*overlap
            if cosine<.23 and not overlap:continue
            matches.append(dict(doc,score=round(score,4),semantic_score=round(cosine,4)))
        matches.sort(key=lambda x:x['score'],reverse=True)
        result=[];counts={}
        for doc in matches:
            key=(doc['source'],str(doc['record_id']))
            if counts.get(key,0)>=2:continue
            counts[key]=counts.get(key,0)+1;result.append(doc)
            if len(result)>=limit:break
        return result
