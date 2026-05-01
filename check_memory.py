import psutil, os

proc = psutil.Process(os.getpid())
print(f"目前這個 Python 進程：{proc.memory_info().rss / 1024 / 1024:.1f} MB")

print("\n=== 所有 Python 進程 ===")
for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cmdline']):
    if p.info['name'] and 'python' in p.info['name'].lower():
        mb = p.info['memory_info'].rss / 1024 / 1024
        cmd = ' '.join(p.info['cmdline'] or [])[-50:]
        print(f"  PID {p.info['pid']:6d} | {mb:7.1f} MB | {cmd}")