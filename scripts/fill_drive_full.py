"""Fill Drive folder 1zdi_ehBIia07bG_O9hPYOqODkfWdl4aX until 14.5GB - run in background."""
import sys, pathlib, time, os, json, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import clip_cafe, phrases
from pathlib import Path
FOLDER_ID = "1zdi_ehBIia07bG_O9hPYOqODkfWdl4aX"
TARGET_BYTES = int(14.5 * 1024**3)
STATE = Path("scripts/.fill_state.json")
if STATE.exists():
    state = json.loads(STATE.read_text())
else:
    state = {"done": [], "failed": [], "total_bytes": 0}
done_set = set(state["done"]); failed_set = set(state["failed"]); total_bytes = state["total_bytes"]
print(f"Resuming: {len(done_set)} done, {len(failed_set)} failed, {total_bytes/1024/1024:.1f}MB")
all_phrases = [(lvl, p) for lvl in phrases.LEVELS for p in phrases.BANK[lvl]]
print(f"BANK {len(all_phrases)} total")
import subprocess
for lvl, phrase in all_phrases:
    if total_bytes >= TARGET_BYTES:
        print(f"TARGET reached {total_bytes/1024/1024:.0f}MB"); break
    text = phrase.text
    if text in done_set or text in failed_set: continue
    print(f"Trying {text!r} [{lvl}]...", flush=True)
    try:
        clip = clip_cafe.find_clip(text)
        path = clip.path; size = path.stat().st_size if path.exists() else 0
        if size == 0: raise RuntimeError("empty clip")
        total_bytes += size; done_set.add(text)
        print(f"  OK {clip.title} {size/1024:.0f}KB total {total_bytes/1024/1024:.1f}MB", flush=True)
        if len(done_set) % 10 == 0:
            try:
                subprocess.run(["git","add","scripts/.fill_state.json"], cwd=".", timeout=5)
                subprocess.run(["git","commit","-m",f"chore: fill progress {len(done_set)} clips","--allow-empty"], cwd=".", timeout=5)
                subprocess.run(["git","push","origin","main"], cwd=".", timeout=15)
            except: pass
        state["done"] = list(done_set); state["failed"] = list(failed_set); state["total_bytes"] = total_bytes
        STATE.write_text(json.dumps(state))
        time.sleep(0.5)
        if len(done_set) % 20 == 0: print(f"--- progress {len(done_set)} clips {total_bytes/1024/1024:.0f}MB ---")
    except Exception as e:
        failed_set.add(text); print(f"  FAIL: {e}", flush=True)
        state["failed"] = list(failed_set); STATE.write_text(json.dumps(state))
        time.sleep(0.5)
print(f"Finished batch: {len(done_set)} clips {total_bytes/1024/1024:.0f}MB")
