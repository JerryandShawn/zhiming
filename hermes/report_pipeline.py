"""Durable, independently timed report delivery and cron-output recovery.

Hermes generates in advance, with deliver=local. This worker alone delivers
to the pre-existing Feishu target. A stable UUID bounds ambiguous retries to
50 minutes, safely inside Feishu's one-hour deduplication window.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from contextlib import contextmanager,closing
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
from archive_store import read_json,locked,transaction
from report_store import store as save_report

TZ=timezone(timedelta(hours=8))
KINDS={'daily':'晨报','weekly':'周报','monthly':'月报','quarterly':'季报'}

def scheduled(kind,date):
    if kind=='weekly' and date.weekday()!=6:return None
    if kind in ('monthly','quarterly') and date.day!=1:return None
    if kind=='quarterly' and date.month not in (1,4,7,10):return None
    return datetime(date.year,date.month,date.day,{'daily':7,'weekly':20,'monthly':9,'quarterly':10}[kind],tzinfo=TZ)

class Pipeline:
    def __init__(self,base,cron_home=None):
        self.base=Path(base);self.base.mkdir(parents=True,exist_ok=True)
        self.path=self.base/'reports.db';self.cron=Path(cron_home or '/root/.hermes/cron')
        self.config=read_json(self.base/'report-pipeline.json',{'enabled':False,'jobs':[]})
        with self.db() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS outbox(
              id TEXT PRIMARY KEY,kind TEXT,date TEXT,due TEXT,job_id TEXT,status TEXT DEFAULT 'waiting',
              content TEXT DEFAULT '',attempts INTEGER DEFAULT 0,first_send REAL DEFAULT 0,
              next_attempt REAL DEFAULT 0,message_id TEXT DEFAULT '',error TEXT DEFAULT '',updated_at TEXT,
              prep_attempts INTEGER DEFAULT 0,prep_retry REAL DEFAULT 0);
              CREATE TABLE IF NOT EXISTS recovered(path TEXT PRIMARY KEY,mtime REAL);
            ''')

    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=15);c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()

    def update(self,ident,**values):
        allowed={'status','content','attempts','first_send','next_attempt','message_id','error','prep_attempts','prep_retry'}
        if not set(values)<=allowed:raise ValueError('Invalid update')
        values['updated_at']=datetime.now(TZ).isoformat(timespec='seconds')
        with self.db() as c:c.execute('UPDATE outbox SET '+','.join(k+'=?' for k in values)+' WHERE id=?',list(values.values())+[ident])

    def seed(self,now):
        with self.db() as c:
            for delta in (0,1):
                date=(now+timedelta(days=delta)).date()
                for job in self.config['jobs']:
                    due=scheduled(job['kind'],date)
                    if not due:continue
                    if self.config.get('start_at') and due<datetime.fromisoformat(self.config['start_at']):continue
                    ident=str(date)+'-'+job['kind']
                    c.execute('INSERT OR IGNORE INTO outbox(id,kind,date,due,job_id,updated_at) VALUES(?,?,?,?,?,?)',
                              (ident,job['kind'],str(date),due.isoformat(),job['id'],now.isoformat()))

    def rows(self):
        with self.db() as c:return [dict(r) for r in c.execute('SELECT * FROM outbox ORDER BY due DESC LIMIT 120')]

    def status(self):
        return {'enabled':bool(self.config.get('enabled')),'timezone':'Asia/Shanghai','prepare_minutes':15,
                'rows':[{k:v for k,v in r.items() if k not in ('content','job_id')} for r in self.rows()]}

    def retry(self,ident):
        row=next((r for r in self.rows() if r['id']==ident),None)
        if not row:raise ValueError('未找到投递记录')
        if row['status'] not in ('generation_failed','delivery_failed'):raise ValueError('本记录无需重试，或送达状态不明，需要先核对飞书记录')
        due=datetime.fromisoformat(row['due'])
        if datetime.now(TZ)-due>timedelta(hours=12):raise ValueError('报告已过投递时段，可在网页阅读归档')
        if row['status']=='generation_failed':self.update(ident,status='waiting',prep_attempts=0,prep_retry=0,error='')
        else:self.update(ident,status='ready',attempts=0,first_send=0,next_attempt=0,error='')

    def recover(self):
        """Recover only outputs backed by a completed execution, never partial files."""
        ledger=self.cron/'executions.db'
        if not ledger.exists():return
        with closing(sqlite3.connect(f'file:{ledger}?mode=ro',uri=True)) as c:
            completed=c.execute("SELECT job_id,started_at,finished_at FROM executions WHERE status='completed' ORDER BY claimed_at DESC LIMIT 500").fetchall()
        arc=read_json(self.base/'archive.json',{})
        existing={(r.get('date'),r.get('type')) for r in arc.get('reports',[])}
        for job in self.config['jobs']:
            folder=self.cron/'output'/job['id']
            for path in sorted(folder.glob('*.md'),reverse=True)[:40]:
                date=path.name[:10];kind=KINDS[job['kind']]
                # v5 reports must pass report_store's structured field validation;
                # a completed LLM markdown response alone cannot bypass this gate.
                if self.config.get('structured_from') and date>=self.config['structured_from']:continue
                if (date,kind) in existing:continue
                # Bind a file to a successful execution interval, not just a successful day.
                def moment(value):
                    try:return datetime.fromtimestamp(float(value),TZ)
                    except (TypeError,ValueError):
                        try:return datetime.fromisoformat(str(value)).astimezone(TZ)
                        except ValueError:return None
                try:stamp=datetime.strptime(path.stem,'%Y-%m-%d_%H-%M-%S').replace(tzinfo=TZ)
                except ValueError:continue
                if not any(j==job['id'] and moment(start) and moment(end) and moment(start)-timedelta(seconds=5)<=stamp<=moment(end)+timedelta(minutes=2) for j,start,end in completed):continue
                raw=path.read_text(encoding='utf-8')
                content=raw.split('\n## Response\n',1)[-1].strip() if '\n## Response\n' in raw else ''
                if len(content)<200 or re.search(r'\[SILENT\]|\[CRON_FAILURE\]|Traceback \(most recent',content):continue
                save_report(self.base/'archive.json',date,kind,content)
                def mark(archive):
                    record=next(r for r in archive['reports'] if r.get('date')==date and r.get('type')==kind)
                    record.update(recovered_from='cron_output',recovered_at=datetime.now(TZ).isoformat(),review_status='historical_unverified')
                transaction(self.base/'archive.json',mark,{})
                existing.add((date,kind))

    def prepare(self,now):
        arc=read_json(self.base/'archive.json',{})
        raw=read_json(self.cron/'jobs.json',{})
        jobs={j['id']:j for j in (raw.get('jobs',[]) if isinstance(raw,dict) else raw)}
        for row in self.rows():
            if row['status'] not in ('waiting','generation_failed'):continue
            due=datetime.fromisoformat(row['due'])
            if now<due-timedelta(minutes=15):continue
            report=next((r for r in arc.get('reports',[]) if r.get('date')==row['date'] and r.get('type')==KINDS[row['kind']]),None)
            needs_structure=bool(self.config.get('structured_from') and row['date']>=self.config['structured_from'])
            structure_ok=report and (not needs_structure or report.get('schema_version')=='5.0' and report.get('validation',{}).get('chart_fields_checked'))
            if structure_ok and len(report.get('content','').strip())>=200:
                url=self.config.get('site_url','https://p.jerrymeng.asia').rstrip('/')+'/#/reports?date='+row['date']
                content=report['content'].strip()+'\n\n完整归档：'+url
                self.update(row['id'],content=content,status='ready',error='');continue
            if now>due+timedelta(hours=12):
                self.update(row['id'],status='expired',error='已超过投递时段；历史内容仍可归档');continue
            job=jobs.get(row['job_id'],{})
            last=str(job.get('last_run_at',''))
            failed=job.get('last_status') not in (None,'ok') and last[:10]==row['date']
            # Don't interrupt an active generation; missed runs are retried after a grace period.
            running=False
            ledger=self.cron/'executions.db'
            if ledger.exists():
                with closing(sqlite3.connect(f'file:{ledger}?mode=ro',uri=True)) as c:
                    running=bool(c.execute("SELECT 1 FROM executions WHERE job_id=? AND status IN ('running','claimed') LIMIT 1",(row['job_id'],)).fetchone())
            if running:continue
            if (failed or now>due+timedelta(minutes=5)) and now.timestamp()>=row['prep_retry']:
                if row['prep_attempts']>=3:
                    self.update(row['id'],status='generation_failed',error='生成未完成，已自动重试3次');continue
                self.update(row['id'],prep_attempts=row['prep_attempts']+1,prep_retry=now.timestamp()+600,error='正在重新准备报告')
                subprocess.run(['hermes','cron','run',row['job_id']],check=True,timeout=40,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def deliver(self,now,transport=None):
        transport=transport or send_feishu
        for row in self.rows():
            if row['status'] not in ('ready','sending','retrying'):continue
            due=datetime.fromisoformat(row['due'])
            if now<due or now.timestamp()<row['next_attempt']:continue
            if row['first_send'] and now.timestamp()-row['first_send']>=3000:
                self.update(row['id'],status='uncertain',error='送达状态未确认，已停止自动重试以避免重复，请核对飞书');continue
            if now>due+timedelta(hours=12):
                self.update(row['id'],status='expired',error='错过当日投递时段，完整报告可在网页阅读');continue
            job=next(j for j in self.config['jobs'] if j['id']==row['job_id'])
            uid=hashlib.sha256(('zhiming-report-v4:'+row['id']).encode()).hexdigest()[:40]
            first=row['first_send'] or now.timestamp()
            self.update(row['id'],status='sending',first_send=first,attempts=row['attempts']+1,next_attempt=now.timestamp()+120)
            try:
                result=transport(job['target'],row['content'],uid)
                self.update(row['id'],status='sent',message_id=result,error='')
            except DeliveryRejected as exc:
                # A rejection of a later retry cannot prove an earlier timed-out send failed.
                if row['status'] in ('retrying','sending'):
                    self.update(row['id'],status='retrying',error='此前投递结果不明，继续限时去重核对',next_attempt=now.timestamp()+120)
                else:
                    final=row['attempts']>=4
                    self.update(row['id'],status='delivery_failed' if final else 'ready',first_send=0,error=str(exc),next_attempt=now.timestamp()+120)
            except Exception:
                self.update(row['id'],status='retrying',error='网络结果不明，使用同一请求编号等待重试')

class DeliveryRejected(RuntimeError):pass

def send_feishu(target,content,uid):
    if not re.fullmatch(r'(oc|ou)_[a-zA-Z0-9]+',target):raise DeliveryRejected('投递目标无效')
    with httpx.Client(timeout=30) as client:
        r=client.post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',json={
            'app_id':os.environ['FEISHU_APP_ID'],'app_secret':os.environ['FEISHU_APP_SECRET']})
        r.raise_for_status();auth=r.json()
        if auth.get('code')!=0:raise DeliveryRejected('飞书身份校验未通过')
        r=client.post('https://open.feishu.cn/open-apis/im/v1/messages',params={'receive_id_type':'chat_id' if target.startswith('oc_') else 'open_id'},
                      headers={'Authorization':'Bearer '+auth['tenant_access_token']},json={'receive_id':target,'msg_type':'text','uuid':uid,
                         'content':json.dumps({'text':content},ensure_ascii=False)})
        # Non-JSON/5xx responses are ambiguous, not proof of rejection.
        data=r.json()
        if data.get('code')!=0:
            if r.status_code>=500:raise RuntimeError('ambiguous upstream error')
            raise DeliveryRejected('飞书拒绝投递，错误码 '+str(data.get('code')))
        return data['data']['message_id']

def tick(base):
    p=Pipeline(base)
    if not p.config.get('enabled'):return
    with locked(p.base/'report-worker'):
        now=datetime.now(TZ);p.seed(now);p.recover();p.prepare(now);p.deliver(datetime.now(TZ))
        state={'at':datetime.now(TZ).isoformat(),'ok':True}
        (p.base/'report-worker-health.json').write_text(json.dumps(state),encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default=os.path.expanduser('~/.hermes/zhiming'))
    args=parser.parse_args();tick(args.base)
