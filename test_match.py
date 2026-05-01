from long_term_memory import get_memory

lm = get_memory()

print(f"目前共 {len(lm._memories)} 筆記憶\n")

print("=== 可能有問題的記憶（問答記錄 / 簡體中文）===")
bad = []
for i, m in enumerate(lm._memories):
    c = m["content"]
    is_bad = False
    reason = ""

    # 問答記錄
    if c.startswith("問：") and "→ 答：" in c:
        is_bad = True
        reason = "問答記錄"

    # 包含簡體中文特徵
    for sc in ["无法", "调试", "没有存储", "获取您的", "协助解答", "请问有其他",
               "帮助你", "确保", "进行", "代码", "运行程序", "以上步骤"]:
        if sc in c:
            is_bad = True
            reason = "簡體回答"
            break

    if is_bad:
        bad.append(i)
        print(f"  [{i}] ({reason}) {c[:80]}")

print(f"\n找到 {len(bad)} 筆問題記憶")

if bad:
    print("\n清除中...")
    lm._memories = [m for i, m in enumerate(lm._memories) if i not in bad]
    lm._save()
    print(f"清除完成，剩餘 {len(lm._memories)} 筆")
else:
    print("記憶庫很乾淨！")

