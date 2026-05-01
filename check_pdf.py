import sqlite3
conn = sqlite3.connect('knowledge_data/knowledge.db')
rows = conn.execute("SELECT id, title, content FROM entries WHERE tags LIKE '%PDF%' LIMIT 5").fetchall()
for r in rows:
    print(f"ID={r[0]} title={r[1]}")
    print(f"  content前100字: {r[2][:100]}")
    print()
