from os_controller import OSController


class TaskCapabilityRegistry:
    """
    AI 已學會的任務技能庫
    """

    def __init__(self, os_controller: OSController):
        self.os = os_controller

        self.registry = {
            "open_ai_agent_folder": self.open_ai_agent_folder,
            "run_tests": self.run_tests,
            "list_workspace": self.list_workspace,
        }

    # ======================
    # 任務定義區
    # ======================

    def open_ai_agent_folder(self):
        return self.os.open_folder(r"C:\Users\ACER\OneDrive\桌面\AI-Agent")

    def run_tests(self):
        return self.os.safe_run(["pytest"])

    def list_workspace(self):
        return self.os.list_dir()

    # ======================
    # 任務呼叫接口
    # ======================

    def execute(self, task_name):

        if task_name not in self.registry:
            return {"error": f"Task not found: {task_name}"}

        try:
            return self.registry[task_name]()
        except Exception as e:
            return {"error": str(e)}