"""Use existing Git credentials without printing or persisting authentication material."""
import json,os,subprocess,urllib.request,urllib.error

def access():
    env=os.environ.copy();env.update(GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
    r=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,env=env,timeout=25)
    if r.returncode:raise RuntimeError('No usable local GitHub credential; interactive login is needed.')
    fields=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
    token=fields.get('password')
    if not token:raise RuntimeError('GitHub credential has no token.')
    def request(path,method='GET',data=None):
        body=json.dumps(data).encode('utf-8') if data is not None else None
        req=urllib.request.Request('https://api.github.com'+path,data=body,method=method,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'fulfillment-project-publisher','Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
        except urllib.error.HTTPError as error:raise RuntimeError('GitHub API status '+str(error.code)+' for '+path) from None
    profile=request('/user')
    if profile.get('login','').lower()!='liyuy-lili':raise RuntimeError('Local credential belongs to a different account; stop to choose the intended login.')
    return request,profile

if __name__=='__main__':
    try:
        request,profile=access()
        repos=request('/user/repos?per_page=50&affiliation=owner')
        print(json.dumps({'login':profile['login'],'repositories':[{'name':r['name'],'private':r['private'],'url':r['html_url']} for r in repos]},ensure_ascii=False))
    except (RuntimeError,subprocess.TimeoutExpired) as error:
        print(json.dumps({'ready':False,'reason':str(error)},ensure_ascii=False))
