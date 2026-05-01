import json
import os
from datetime import datetime

EPISODIC_DB = "episodic_memory.json"


class EpisodicMemory:

    def __init__(self):
        self.db = self._load()

    def _load(self):
        if not os.path.exists(EPISODIC_DB):
            return []
        with open(EPISODIC_DB, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self):
        with open(EPISODIC_DB, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=2)

    def store(self, input_text, response, action=None):

        episode = {
            "time": datetime.now().isoformat(),
            "input": input_text,
            "response": response,
            "action": action
        }

        self.db.append(episode)

        # 控制大小
        if len(self.db) > 1000:
            self.db = self.db[-1000:]

        self._save()

    def search_recent(self, n=5):
        return self.db[-n:]

    def search_keyword(self, keyword):
        return [e for e in self.db if keyword in e["input"]]