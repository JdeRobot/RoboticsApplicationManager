import re
import os
import subprocess
import sys


class Lint:

    def clean_pylint_output(self, result, warnings=False):

        # result = result.replace(os.path.basename(code_file_name), 'user_code')
        # Define the patterns to remove
        patterns = [
            r":[0-9]+:[0-9]+: C[0-9]{4}:.*",  # Convention messages
            r":[0-9]+:[0-9]+: W[0-9]{4}:.*",  # Warning messages
            r":[0-9]+:[0-9]+: R[0-9]{4}:.*",  # Refactor messages
            r":[0-9]+:[0-9]+: error.*EOF.*",  # Unexpected EOF error
            r":[0-9]+:[0-9]+: E1101:.*Module 'ompl.*",  # ompl E1101 error
            r":[0-9]+:[0-9]+:.*value.*argument.*unbound.*method.*",  # No value for argument 'self' error
            r":[0-9]+:[0-9]+: E1111:.*",  # Assignment from no return error
            r":[0-9]+:[0-9]+: E1136:.*"  # E1136 until issue is resolved
        ]

        if not warnings:
            # Remove convention, refactor, and warning messages if warnings are not desired
            for pattern in patterns[:3]:
                result = re.sub(r"^[^:]*" + pattern, '', result, flags=re.MULTILINE)
        
        # Remove specific errors
        for pattern in patterns[3:]:
            result = re.sub(r"^[^:]*" + pattern, '', result, flags=re.MULTILINE)

        
        result = re.sub(r"^\s*$\n", '', result, flags=re.MULTILINE)

        # Transform the remaining error messages
        result = re.sub(r"^[^:]+:(\d+):\d+: \w*:\s*(.*)", r"line \1: \2", result, flags=re.MULTILINE)

        if result.strip() and re.search(r"line", result):
            result = "Traceback (most recent call last):\n" + result.strip()

        return result

    def append_rating_if_missing(self, result):
        rating_message = "-----------------------------------\nYour code has been rated at 0.00/10"
        
        # Check if the rating message already exists
        if not re.search(r"Your code has been rated", result):
            result += "\n" + rating_message
        if not re.search(r"error", result) and not re.search(r"undefined", result):
            result = ''

        return result

    def evaluate_code(self, code, exercise_id, ros_version, warnings=False):
        try:
            code = re.sub(r'from HAL import HAL', 'from hal import HAL', code)
            code = re.sub(r'from GUI import GUI', 'from gui import GUI', code)
            code = re.sub(r'from MAP import MAP', 'from map import MAP', code)
            code = re.sub(r'\nimport cv2\n', '\nfrom cv2 import cv2\n', code)

            # Avoids EOF error when iterative code is empty (which prevents other errors from showing)
            while_position = re.search(
                r'[^ ]while\s*\(\s*True\s*\)\s*:|[^ ]while\s*True\s*:|[^ ]while\s*1\s*:|[^ ]while\s*\(\s*1\s*\)\s*:', code)
            sequential_code = code[:while_position.start()]
            iterative_code = code[while_position.start():]
            iterative_code = re.sub(
                r'[^ ]while\s*\(\s*True\s*\)\s*:|[^ ]while\s*True\s*:|[^ ]while\s*1\s*:|[^ ]while\s*\(\s*1\s*\)\s*:', '\n', iterative_code, 1)
            iterative_code = re.sub(r'^[ ]{4}', '', iterative_code, flags=re.M)
            code = sequential_code + iterative_code
            
            f = open("user_code.py", "w")
            f.write(code)
            f.close()

            command = ""
            if "humble" in str(ros_version):                
                command = f"export PYTHONPATH=$PYTHONPATH:/RoboticsAcademy/exercises/static/exercises/{exercise_id}/python_template/ros2_humble; python3 RoboticsAcademy/src/manager/manager/lint/pylint_checker.py"
            else:
                command = f"export PYTHONPATH=$PYTHONPATH:/RoboticsAcademy/exercises/static/exercises/{exercise_id}/python_template/ros1_noetic; python3 RoboticsAcademy/src/manager/manager/lint/pylint_checker.py"
            
            ret = subprocess.run(
                command,
                capture_output=True, 
                text=True,
                shell=True
            )
            
            result = ret.stdout
            result = result + "\n"

            cleaned_result = self.clean_pylint_output(result)
            final_result = self.append_rating_if_missing(cleaned_result)

            return final_result.strip()
        except Exception as ex:
            print(ex)
