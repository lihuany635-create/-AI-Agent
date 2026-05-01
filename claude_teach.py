# claude_teach.py
import sys, pathlib, datetime
sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

from long_term_memory import get_memory
mem = get_memory()

LESSONS = [
    {
        "topic": "handle\u65b9\u6cd5\u7684\u5224\u65b7\u9806\u5e8f",
        "method": "\u5728handle\u65b9\u6cd5\u88e1\uff0c\u5efa\u7acb/\u522a\u9664/\u91cd\u547d\u540d\u7b49\u64cd\u4f5c\u578b\u6307\u4ee4\u8981\u653e\u5728\u67e5\u770b\u578b\u6307\u4ee4\u524d\u9762\u5224\u65b7",
        "reason": "\u300c\u5efa\u7acb\u8cc7\u6599\u593e \u6e2c\u8a66\u300d\u5305\u542b\u300c\u8cc7\u6599\u593e\u300d\uff0c\u5982\u679c\u67e5\u770b\u5224\u65b7\u5728\u524d\u9762\u6703\u8aa4\u5224\u70ba\u67e5\u770b\u6307\u4ee4",
        "tags": ["claude_teach", "python", "handle"],
        "importance": 9,
    },
    {
        "topic": "\u95dc\u9375\u5b57\u5339\u914d\u7684\u9677\u9631",
        "method": "\u5148\u5224\u65b7\u66f4\u5177\u9ad4\u7684\u95dc\u9375\u5b57\uff0c\u518d\u5224\u65b7\u66f4\u5ee3\u6cdb\u7684\u95dc\u9375\u5b57",
        "reason": "\u5ee3\u6cdb\u7684\u95dc\u9375\u5b57\u5982\u300c\u8cc7\u6599\u593e\u300d\u6703\u8aa4\u5339\u914d\u4e0d\u76f8\u95dc\u7684\u6307\u4ee4\uff0c\u5c0e\u81f4\u57f7\u884c\u932f\u8aa4\u7684\u884c\u70ba",
        "tags": ["claude_teach", "python", "keyword"],
        "importance": 9,
    },
    {
        "topic": "process_input\u6deb\u6212\u5668\u9806\u5e8f",
        "method": "\u6deb\u6212\u5668\u512a\u5148\u9806\u5e8f\uff1a\u7cfe\u6b63\u5b78\u7fd2>\u684c\u9762\u63a7\u5236>\u6a94\u6848\u7ba1\u7406>\u81ea\u6211\u8a3a\u65b7>\u81ea\u4e3b\u958b\u767c>\u7d42\u7aef\u6307\u4ee4>\u4e00\u822c\u554f\u7b54",
        "reason": "\u512a\u5148\u8655\u7406\u4e0d\u9700\u8981LLM\u7684\u76f4\u63a5\u884c\u52d5\uff0c\u6700\u5f8c\u624d\u4ea4\u7d66LLM\u63a8\u8ad6\uff0c\u6e1b\u5c11\u7b49\u5f85\u6642\u9593",
        "tags": ["claude_teach", "architecture"],
        "importance": 9,
    },
    {
        "topic": "\u53cd\u5c04\u8a18\u61b6\u7684\u5f71\u97ff",
        "method": "\u5982\u679c\u7acb\u4e00\u76f4\u7528\u820a\u7b54\u6848\u56de\u7b54\uff0c\u5148\u6e05\u9664 reflex_memory.json \u624d\u80fd\u8b93\u65b0\u529f\u80fd\u751f\u6548",
        "reason": "\u53cd\u5c04\u8a18\u61b6\u662f\u6700\u9ad8\u512a\u5148\u7684\u5feb\u901f\u56de\u7b54\u6a5f\u5236\uff0c\u6703\u7e5e\u904e\u6240\u6709\u5f8c\u4f86\u52a0\u5165\u7684\u529f\u80fd",
        "tags": ["claude_teach", "reflex_memory"],
        "importance": 9,
    },
    {
        "topic": "Windows\u7de8\u78bc\u554f\u984c",
        "method": "Python\u6a94\u6848\u8981\u7528 utf-8 \u5132\u5b58\uff0c\u5728\u6a94\u6848\u958b\u982d\u52a0 sys.stdout.reconfigure(encoding='utf-8')",
        "reason": "Windows\u9810\u8a2d cp950 \u7de8\u78bc\uff0c\u4e2d\u6587\u5728\u8b80\u53d6\u6642\u6703\u8b8a\u4e82\u78bc\uff0c\u5c0e\u81f4\u95dc\u9375\u5b57\u5339\u914d\u5931\u6557",
        "tags": ["claude_teach", "encoding"],
        "importance": 9,
    },
    {
        "topic": "patch\u8173\u672c\u8a2d\u8a08",
        "method": "\u4fee\u6539\u7a0b\u5f0f\u78bc\u6642\uff0c\u5148\u5099\u4efd\uff0c\u518d\u4fee\u6539\uff0c\u518d\u7528 ast.parse \u9a57\u8b49\uff0c\u932f\u8aa4\u5c31\u81ea\u52d5\u9084\u539f",
        "reason": "\u76f4\u63a5\u4fee\u6539\u7a0b\u5f0f\u78bc\u6709\u8a9e\u6cd5\u932f\u8aa4\u7684\u98a8\u96aa\uff0c\u5099\u4efd+\u9a57\u8b49+\u9084\u539f\u78ba\u4fdd\u7cfb\u7d71\u4e0d\u6703\u58de\u63a1",
        "tags": ["claude_teach", "patch"],
        "importance": 8,
    },
]

print("="*40)
print("Claude Teaching System")
print("="*40)
ok = 0
for lesson in LESSONS:
    content = f"[Topic]{lesson['topic']}\n[Method]{lesson['method']}\n[Reason]{lesson['reason']}"
    mem.store(content, tags=lesson['tags'], importance=lesson['importance'], source="claude")
    print(f"[OK] {lesson['topic']}")
    ok += 1

print(f"\nDone! {ok}/{len(LESSONS)} stored. Total: {len(mem._memories)}")

