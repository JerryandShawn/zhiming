"""Pure Feishu transport. Identity and payload validation belong to Core."""
import json
import os
import re
import httpx
from .delivery import TransportRejected


class FeishuTransport:
    def __call__(self,target,content,operation_id):
        if not re.fullmatch(r'(oc|ou)_[a-zA-Z0-9]+',target):raise TransportRejected('飞书目标格式无效')
        if not isinstance(content,str) or not content.strip():raise TransportRejected('投递正文为空')
        with httpx.Client(timeout=30) as client:
            response=client.post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',json={
                'app_id':os.environ['FEISHU_APP_ID'],'app_secret':os.environ['FEISHU_APP_SECRET']})
            response.raise_for_status();authorization=response.json()
            if authorization.get('code')!=0:raise TransportRejected('飞书身份校验拒绝')
            response=client.post('https://open.feishu.cn/open-apis/im/v1/messages',params={'receive_id_type':'chat_id' if target.startswith('oc_') else 'open_id'},
                headers={'Authorization':'Bearer '+authorization['tenant_access_token']},json={'receive_id':target,'msg_type':'text','uuid':operation_id,'content':json.dumps({'text':content},ensure_ascii=False)})
            if response.status_code>=500:raise RuntimeError('DELIVERY_UNCERTAIN')
            data=response.json()
            if data.get('code')!=0:raise TransportRejected('飞书明确拒绝投递')
            return data['data']['message_id']
