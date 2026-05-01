# bmi_calculator.py

from math import sqrt  # 統計模組內 sqrt 函式計算 BMI 需要的平方根運算

class BMICalculator:
    """
    一個包含BMI計算邏輯和健康狀態判斷的類別.

    在這個程式中,我們會使用使用者輸入的身高和體重來計算身體質量指數(BMI),並且根據BMI結果進一步評估使用者的健康狀況.
    """

    def calculate_bmi(self, height: float, weight: float) -> (float, str):
        """
        計算使用者的BMI.

        :param height: 使用者的身高,單位為公尺(m).
        :param weight: 使用者的體重,單位為公斤(kg).
        :return: 一組值,包含計算結果的BMI和相對應的健康狀態描述.
        """
        
        # 計算BMI
        bmi = weight / (height ** 2)
        
        # 根據BMI結果評估健康狀況並回傳相應的描述
        if bmi < 18.5:
            health_status = '低於正常範圍'