import json
from pathlib import Path


class SkillLearningEngine:

    def __init__(self, registry):
        self.registry = registry
        self.file = Path("skill_memory.json")
        self.skills = self._load()

    def _load(self):
        if self.file.exists():
            return json.loads(self.file.read_text(encoding="utf-8"))
        return {"skills": {}}

    def _save(self):
        self.file.write_text(
            json.dumps(self.skills, indent=2),
            encoding="utf-8"
        )

    def learn(self, phrase, task_name):
        self.skills["skills"][phrase.lower()] = task_name
        self._save()

    def match(self, text):
        text = text.lower()
        for phrase, task in self.skills["skills"].items():
            if phrase in text:
                return self.registry.execute(task)
        return None