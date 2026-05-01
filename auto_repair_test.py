from error_detector import ErrorDetector
from repair_engine import RepairEngine
from reasoning_supervisor import ReasoningSupervisor
from repair_trigger import RepairTrigger
from repair_loop_controller import RepairLoopController


detector = ErrorDetector()
engine = RepairEngine()
supervisor = ReasoningSupervisor()
trigger = RepairTrigger(engine, supervisor)

loop = RepairLoopController(detector, trigger)

result = loop.run("test_bug.py")

print("LOOP RESULT:", result)