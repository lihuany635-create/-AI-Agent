import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from long_term_memory import get_memory
lm = get_memory()

before = len(lm._memories)
lm._memories = [m for m in lm._memories if "auto_learn" not in m.get("tags", [])]
after = len(lm._memories)
lm._save()

print(f"deleted {before - after} auto-learned memories")
print(f"remaining: {after}")

