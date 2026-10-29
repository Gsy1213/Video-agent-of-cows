import base64,hashlib,hmac,json,os
from .config import DATA

keypath=DATA/'.cursor-key'
if not keypath.exists():
    try:
        with keypath.open('xb') as f:f.write(os.urandom(32))
    except FileExistsError:pass
KEY=keypath.read_bytes()
def paginate(items,limit=20,cursor=None,filters=None):
    digest=hashlib.sha256(json.dumps(filters or {},sort_keys=True).encode()).hexdigest()[:16];offset=0
    if cursor:
        try:
            raw=base64.urlsafe_b64decode(cursor.encode());body,mac=raw[:-32],raw[-32:]
            if not hmac.compare_digest(hmac.digest(KEY,body,'sha256'),mac):raise ValueError()
            data=json.loads(body)
            if data['q']!=digest:raise ValueError()
            offset=data['n']
        except Exception:raise ValueError('INVALID_CURSOR')
    next_cursor=None
    if offset+limit<len(items):
        body=json.dumps({'q':digest,'n':offset+limit}).encode();next_cursor=base64.urlsafe_b64encode(body+hmac.digest(KEY,body,'sha256')).decode()
    return {'items':items[offset:offset+limit],'next_cursor':next_cursor}
