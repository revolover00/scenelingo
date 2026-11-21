"""GitHub Action uploader: download clip + upload to Drive via Service Account."""
import os, json, pathlib, time, sys
sys.path.insert(0, ".")
import clip_cafe, phrases
from pathlib import Path
folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "1zdi_ehBIia07bG_O9hPYOqODkfWdl4aX")
sa_json = os.environ.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")
if not sa_json:
    print("No service account, running in dry-run (download only)")
    sa_json = None
else:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = service_account.Credentials.from_service_account_info(json.loads(sa_json), scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=creds)
    # verify folder
    try:
        drive.files().get(fileId=folder_id, fields="id,name").execute()
        print(f"Drive folder OK: {folder_id}")
    except Exception as e:
        print(f"Drive folder error: {e}"); sys.exit(1)

TARGET = int(14.5 * 1024**3)
state_path = Path("scripts/.fill_state.json")
state = json.loads(state_path.read_text()) if state_path.exists() else {"done":[],"failed":[],"total_bytes":0}
done = set(state["done"]); failed=set(state.get("failed",[])); total=state.get("total_bytes",0)
print(f"Resume {len(done)} done {total/1024/1024:.1f}MB")
# Get already uploaded names to avoid re-upload
existing = set()
if sa_json:
    try:
        resp = drive.files().list(q=f"'{folder_id}' in parents and trashed=false", fields="files(name)", pageSize=1000).execute()
        existing = {f["name"] for f in resp.get("files",[])}
        print(f"Already in Drive: {len(existing)} files")
    except Exception as e: print(f"List error {e}")

for lvl, ph in [(l,p) for l in phrases.LEVELS for p in phrases.BANK[l]]:
    if total >= TARGET: break
    txt = ph.text
    name = f"{txt[:80]}.mp4"
    if txt in done or name in existing: continue
    if txt in failed: continue
    try:
        print(f"Trying {txt!r}...", flush=True)
        clip = clip_cafe.find_clip(txt)
        path = clip.path
        sz = path.stat().st_size
        if sa_json:
            media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True)
            drive.files().create(body={"name": name, "parents":[folder_id]}, media_body=media, fields="id").execute()
            print(f" Uploaded {name} {sz/1024:.0f}KB")
        else:
            print(f" Dry-run {name} {sz/1024:.0f}KB")
        done.add(txt); total+=sz
        state.update({"done":list(done),"failed":list(failed),"total_bytes":total})
        state_path.write_text(json.dumps(state))
        time.sleep(1)
        if len(done) % 10 == 0:
            # push progress
            import subprocess
            subprocess.run(["git","config","user.email","bot@scenelingo"], check=False)
            subprocess.run(["git","config","user.name","fill-bot"], check=False)
            subprocess.run(["git","add","scripts/.fill_state.json"], check=False)
            subprocess.run(["git","commit","-m",f"chore: fill {len(done)} clips {total/1024/1024:.0f}MB"], check=False)
            subprocess.run(["git","push","origin","main"], check=False)
            if total >= TARGET: break
    except Exception as e:
        print(f" FAIL {e}"); failed.add(txt)
        state["failed"]=list(failed); state_path.write_text(json.dumps(state))
        time.sleep(1)
print(f"Done {len(done)} clips {total/1024/1024:.0f}MB")
