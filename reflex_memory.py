import json
import os

REFLEX_FILE = "reflex_memory.json"


class ReflexMemory:

    def __init__(self):
        self.memory = self._load()

    def _load(self):
        if not os.path.exists(REFLEX_FILE):
            return {}
        with open(REFLEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self):
        with open(REFLEX_FILE, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=2)

    def get(self, text):
        entry = self.memory.get(text)
        if not entry:
            return None
        if entry["confidence"] < 0.2:
            return None
        return entry["response"]

    def learn(self, text, response):

        if text not in self.memory:
            self.memory[text] = {
                "response": response,
                "confidence": 0.3
            }
        else:
            self.memory[text]["confidence"] += 0.1

        self._save()

    def punish(self, text):
        if text in self.memory:
            self.memory[text]["confidence"] -= 0.2
            if self.memory[text]["confidence"] <= 0:
                del self.memory[text]
        self._save()