import os, sqlite3
sys.setrecursionlimit(1000)

class Window:
    def __init__(self):
        self.setWindowTitle("BMI 计算器")
        
    def createWindow(self):
        main = pyqt6.Window()
        main.setWidget(self)
        main.show