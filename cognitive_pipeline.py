class CognitivePipeline:

    def __init__(self, reflex, router, core):
        self.reflex = reflex
        self.router = router
        self.core = core

    def process(self, text):

        # 1️⃣ Reflex
        r = self.reflex.analyze(text)
        if r:
            return r

        # 2️⃣ Intent / Task
        t = self.router.route(text)
        if t is not None:
            return f"⚙ 任務執行：{t}"

        # 3️⃣ Cognitive
        return self.core.reason(text)