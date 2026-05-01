import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QGridLayout, QDialogButtonBox, QMessageBox, QTextEdit


class BMIcalculator(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 初始化 GUI 元件和參數
        
        self.init_ui()
    
    def init_ui(self):
        widget = QWidget(self)
        self.setCentralWidget(widget)

        layout = QVBoxLayout()

        label_height = QLabel("請輸入身高(米):")
        self.line_edit_height = QLineEdit()
        label_weight = QLabel("請輸入體重(公斤):")
        self.line_edit_weight = QLineEdit()
        
        calculate_button = QPushButton("計算 BMI")
        calculate_button.clicked.connect(self.calculate_bmi)
        health_status_label = QLabel("健康狀態:")
        
        layout.addWidget(label_height)
        layout.addWidget(self.line_edit_height)
        layout.addWidget(label_weight)
        layout.addWidget(self.line_edit_weight)
        layout.addWidget(calculate_button)
        layout.addWidget(health_status_label)

        widget.setLayout(layout)