"""Real HTTP/OpenAI acceptance on a disposable container, never the business volume."""
import argparse
import json
import secrets
import subprocess
import time
from pathlib import Path
import requests


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--container',required=True)
    parser.add_argument('--base-url',default='http://127.0.0.1:18000')
    parser.add_argument('--output',default='docs/final_live_smoke.json')
    args=parser.parse_args()
    if args.container != 'rag-final-acceptance':
        raise SystemExit('Only the dedicated disposable acceptance container is allowed.')
    password=secrets.token_urlsafe(24)
    code="import sys; from app.db.database import init_db; from app.services.auth_service import create_user; init_db(); create_user('admin',sys.stdin.read(),'admin',bootstrap=True)"
    proc=subprocess.run(['docker','exec','-i',args.container,'python','-c',code],input=password,text=True,capture_output=True)
    if proc.returncode: raise RuntimeError('Isolated administrator initialization failed.')
    checks=[]
    def check(name,condition):
        checks.append({'scenario':name,'passed':bool(condition)})
    def call(method,path,token=None,**kwargs):
        headers={'Authorization':'Bearer '+token} if token else {}
        return requests.request(method,args.base_url+path,headers=headers,timeout=180,**kwargs)
    def login(name):
        r=call('POST','/auth/login',json={'username':name,'password':password});r.raise_for_status()
        return r.json()['access_token']
    admin=login('admin')
    for name in ['alice','bob']:
        call('POST','/admin/users',admin,json={'username':name,'password':password,'role':'user'}).raise_for_status()
    alice,bob=login('alice'),login('bob')
    check('unauthenticated API rejected',call('GET','/documents/list').status_code==401)
    fixtures=[('alice_private.txt',b'Internal authorization policy. The confidential authorization code is ZEBRA_5839. Never share this code outside the authorized team.',alice),
              ('robot_manual.txt',b'Robot maintenance procedure. Before maintenance, isolate the main power supply and lock the power switch. Press the green button to start the motor after maintenance.',bob)]
    ids=[]
    for name,body,token in fixtures:
        r=call('POST','/documents/upload',token,files={'file':(name,body,'text/plain')});r.raise_for_status()
        data=r.json(); ids.append(data['document_id']);check('upload indexed '+name,data['status']=='indexed')
    private_id,robot_id=ids
    check('private document hidden',private_id not in json.dumps(call('GET','/documents/list',bob).json()))
    check('private delete rejected',call('DELETE','/documents/'+private_id,bob).status_code==404)
    check('private rebuild rejected',call('POST','/documents/'+private_id+'/rebuild',bob).status_code==404)
    check('forged document scope rejected',call('POST','/chat/query',bob,json={'question':'code','document_ids':[private_id]}).status_code==403)
    for mode in ['vector','bm25','hybrid']:
        r=call('POST','/chat/query',bob,json={'question':'What is the confidential authorization code?','retrieval_mode':mode});r.raise_for_status()
        check(mode+' private evidence excluded','ZEBRA_5839' not in r.text and 'alice_private.txt' not in r.text and private_id not in r.text)
    call('PATCH','/documents/'+private_id+'/visibility',admin,json={'visibility':'shared'}).raise_for_status()
    check('shared document readable',call('GET','/documents/'+private_id,bob).status_code==200)
    check('shared document still cannot be deleted',call('DELETE','/documents/'+private_id,bob).status_code==404)
    for mode in ['vector','bm25','hybrid']:
        r=call('POST','/chat/query',bob,json={'question':'What is the confidential authorization code?','retrieval_mode':mode,'document_ids':[private_id]});r.raise_for_status()
        data=r.json();check(mode+' shared answer and citation','ZEBRA_5839' in data['answer'] and any(s['document_id']==private_id for s in data['sources']))
    r=call('POST','/chat/query',bob,json={'question':'维护机器人之前应该如何处理主电源？','retrieval_mode':'hybrid','document_ids':[robot_id]});r.raise_for_status()
    data=r.json();check('Chinese question English document',bool(data['sources']) and data['verification']['status']=='PASS' and any(w in data['answer'] for w in ['切断','断开','隔离']))
    r=call('POST','/chat/query',bob,json={'question':'What is the unknown employee monthly salary?','retrieval_mode':'hybrid','document_ids':[robot_id]});r.raise_for_status()
    check('unsupported question refused',r.json()['sources']==[])
    call('PATCH','/documents/'+private_id+'/visibility',admin,json={'visibility':'private'}).raise_for_status()
    check('revoked shared history hidden','ZEBRA_5839' not in call('GET','/chat/history',bob).text)
    check('own rebuild',call('POST','/documents/'+robot_id+'/rebuild',bob).json()['success'])
    subprocess.run(['docker','restart',args.container],capture_output=True,check=True)
    for _ in range(40):
        try:
            if call('GET','/health').status_code==200:break
        except requests.RequestException: pass
        time.sleep(1)
    bob=login('bob')
    check('restart preserves user document and permission',call('GET','/documents/'+robot_id,bob).status_code==200 and call('GET','/documents/'+private_id,bob).status_code==404)
    check('own document delete',call('DELETE','/documents/'+robot_id,bob).json()['success'])
    call('POST','/auth/logout',bob).raise_for_status()
    check('logout revokes session',call('GET','/auth/me',bob).status_code==401)
    report={'checks':checks,'passed':sum(c['passed'] for c in checks),'total':len(checks),'scope':'Disposable container and synthetic fixtures; real OpenAI embedding/generation/verification.'}
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'failed':[c['scenario'] for c in checks if not c['passed']]}))
    if report['passed']!=report['total']: raise SystemExit(1)

if __name__=='__main__':main()
