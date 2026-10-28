"""Throwaway Drive probe. Mirrors the app's web flow (one consent: openid email profile + drive.readonly, offline).
Run:  GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... uv run --no-project --with google-auth-oauthlib --with requests \
        python drive_probe.py --folder-id <FOLDER_ID> [--wait 60]
Redirect URI registered on the client must be exactly http://localhost:8000/auth/callback"""
import os, sys, json, time, argparse, threading, secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import AuthorizedSession, Request
SCOPES=["openid","https://www.googleapis.com/auth/userinfo.email","https://www.googleapis.com/auth/userinfo.profile","https://www.googleapis.com/auth/drive.readonly"]
REDIRECT="http://localhost:8000/auth/callback"; API="https://www.googleapis.com/drive/v3"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"]="1"   # Google may reorder/alias scopes (email -> userinfo.email)
def get_creds():
    cfg={"web":{"client_id":os.environ["GOOGLE_CLIENT_ID"],"client_secret":os.environ["GOOGLE_CLIENT_SECRET"],
        "auth_uri":"https://accounts.google.com/o/oauth2/v2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":[REDIRECT]}}
    flow=Flow.from_client_config(cfg,scopes=SCOPES,redirect_uri=REDIRECT)
    state=secrets.token_urlsafe(16)
    url,_=flow.authorization_url(access_type="offline",prompt="consent",state=state)   # prompt=consent forces a refresh token every time
    got={}
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q=parse_qs(urlparse(self.path).query)
            if urlparse(self.path).path!="/auth/callback": self.send_response(404); self.end_headers(); return
            got.update({k:v[0] for k,v in q.items()}); self.send_response(200); self.end_headers(); self.wfile.write(b"OK, return to the terminal.")
        def log_message(self,*a): pass
    srv=HTTPServer(("localhost",8000),H); print("\nOpen this URL in a browser:\n"+url+"\n")
    while "code" not in got and "error" not in got: srv.handle_request()
    if "error" in got: sys.exit("OAuth error: "+got["error"])
    assert got["state"]==state, "state mismatch"
    flow.fetch_token(code=got["code"]); return flow.credentials
def j(r):
    if r.status_code>=400: print("HTTP",r.status_code,r.text[:400])
    r.raise_for_status(); return r.json()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--folder-id",required=True); ap.add_argument("--wait",type=int,default=60); a=ap.parse_args()
    c=get_creds(); print("granted scopes:",sorted(c.scopes or []))
    print("refresh_token present:",bool(c.refresh_token),"| expires in s:",int((c.expiry-__import__('datetime').datetime.utcnow()).total_seconds()))
    s=AuthorizedSession(c)
    print("userinfo:",j(s.get("https://openidconnect.googleapis.com/v1/userinfo")))
    f=j(s.get(f"{API}/files/{a.folder_id}",params={"fields":"id,name,mimeType,parents","supportsAllDrives":"true"})); print("folder:",f)
    # 1) token FIRST (spec §6 order), 2) then list
    tok=j(s.get(f"{API}/changes/startPageToken",params={"supportsAllDrives":"true"}))["startPageToken"]; print("startPageToken:",tok)
    files=[]; pt=None
    while True:
        p={"q":f"'{a.folder_id}' in parents and trashed=false","pageSize":100,"fields":"nextPageToken,files(id,name,mimeType,md5Checksum,size,modifiedTime,parents,trashed)",
           "supportsAllDrives":"true","includeItemsFromAllDrives":"true","orderBy":"name"}
        if pt: p["pageToken"]=pt
        d=j(s.get(f"{API}/files",params=p)); files+=d["files"]; pt=d.get("nextPageToken")
        if not pt: break
    print(f"files.list: {len(files)} item(s)")
    for x in files[:25]: print("  ",x["id"],x["mimeType"],x.get("size"),x.get("md5Checksum"),x["name"])
    first=next((x for x in files if not x["mimeType"].startswith("application/vnd.google-apps")),None)
    if first:
        r=s.get(f"{API}/files/{first['id']}",params={"alt":"media","supportsAllDrives":"true"},stream=True); n=0
        for chunk in r.iter_content(65536): n+=len(chunk)
        print("alt=media streamed",first["name"],"status",r.status_code,"bytes",n,"content-type",r.headers.get("content-type"))
    # 3) poll changes twice
    def poll(tok):
        out=[]
        while True:
            d=j(s.get(f"{API}/changes",params={"pageToken":tok,"pageSize":100,"includeRemoved":"true","supportsAllDrives":"true","includeItemsFromAllDrives":"true",
              "fields":"nextPageToken,newStartPageToken,changes(changeType,fileId,removed,time,file(id,name,mimeType,md5Checksum,trashed,parents))"}))
            out+=d["changes"]
            if "nextPageToken" in d: tok=d["nextPageToken"]
            else: return out,d["newStartPageToken"]
    for i in (1,2):
        if i==2:
            print(f"\n>>> Now drop/move/trash a file in the folder within {a.wait}s ..."); time.sleep(a.wait)
        t0=time.time(); ch,tok=poll(tok); dt=time.time()-t0
        print(f"poll {i}: {len(ch)} change(s) in {dt*1000:.0f} ms, next token {tok}")
        for x in ch:
            fl=x.get("file") or {}; inf=a.folder_id in (fl.get("parents") or [])
            print("   ",x["changeType"],"removed" if x.get("removed") else "", x["fileId"],fl.get("name"),"trashed="+str(fl.get("trashed")),"IN_FOLDER" if inf else "other-folder")
    # 4) prove the refresh token works (this is what the worker does every poll cycle)
    c.expiry=None; c.refresh(Request()); print("\nrefresh with stored refresh_token OK; new access token expires",c.expiry)
main()
