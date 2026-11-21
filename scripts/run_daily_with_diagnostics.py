"""Run the daily job and expose a redacted failure summary as a check annotation."""
import os
import re
import subprocess
import sys
from collections import deque
from urllib.parse import urlsplit

process = subprocess.Popen(
    [sys.executable, sys.argv[1] if len(sys.argv) > 1 else "daily_job.py"], stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1,
)
tail = deque(maxlen=25)
assert process.stdout is not None
for line in process.stdout:
    print(line, end="", flush=True)
    tail.append(line.rstrip())
returncode = process.wait()
if returncode:
    summary = "\n".join(tail)
    for name in ("BOT_TOKEN", "DATABASE_URL", "GROQ_API_KEY"):
        secret = os.environ.get(name, "")
        if secret:
            summary = summary.replace(secret, "[REDACTED]")
            if name == "DATABASE_URL":
                parts = urlsplit(secret)
                for value in (parts.username, parts.password, parts.hostname):
                    if value:
                        summary = summary.replace(value, "[REDACTED]")
    summary = re.sub(r'https?://\S+', '[URL]', summary)
    summary = summary[-5000:].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print(f"::error title=Daily job failed::{summary}", flush=True)
sys.exit(returncode)
