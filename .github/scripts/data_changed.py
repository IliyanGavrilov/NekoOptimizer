# Prints how many fetched data files really changed, ignoring the "fetched" date stamps
# every fetch rewrites - otherwise each daily run would commit and redeploy for nothing.

import json
import subprocess

DATA = "neko/data"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def unstamped(doc):
    if isinstance(doc, dict):
        return {key: unstamped(value) for key, value in doc.items() if key != "fetched"}
    if isinstance(doc, list):
        return [unstamped(value) for value in doc]
    return doc


changed = git("ls-files", "--others", "--exclude-standard", "--", DATA).split()
for name in git("diff", "--name-only", "--", DATA).split():
    with open(name, encoding="utf-8") as fresh:
        now = json.load(fresh)
    if unstamped(json.loads(git("show", f"HEAD:{name}"))) != unstamped(now):
        changed.append(name)

print(len(changed))
