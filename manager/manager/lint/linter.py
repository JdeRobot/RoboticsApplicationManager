import re
import os
import subprocess

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

    def evaluate_code(self, code, ros_version, warnings=False, py_lint_source="pylint_checker.py"):
        try:
            code = re.sub(r'from HAL import HAL', 'from hal import HAL', code)
            code = re.sub(r'from GUI import GUI', 'from gui import GUI', code)
            code = re.sub(r'from MAP import MAP', 'from map import MAP', code)
            code = re.sub(r'\nimport cv2\n', '\nfrom cv2 import cv2\n', code)

            # Avoids EOF error when iterative code is empty (which prevents other errors from showing)
            loop_regex = (
                r'[^ ]while\s*\(\s*True\s*\)\s*:|'
                r'[^ ]while\s*True\s*:|'
                r'[^ ]while\s*1\s*:|'
                r'[^ ]while\s*\(\s*1\s*\)\s*:|'
                r'rclpy\.spin\(\s*\w+\s*\)|'
                r'rclpy\.spin_once\(\s*\w+\s*.*?\)'
                
            )
            loop_match = re.search(loop_regex, code)

            if loop_match is None:
                return "ERROR: No event loop found. Add 'while True:', 'rclpy.spin(node)', or 'rclpy.spin_once(node)'"
            
            if "rclpy.spin" in loop_match.group() or "rclpy.spin_once" in loop_match.group():
                # Keep the code as-is; don't modify it
                pass
            else:
                # Modify code for while True (add frequency control)
                sequential_code = code[:loop_match.start()]
                iterative_code = code[loop_match.start():]
                iterative_code = re.sub(loop_regex, '\n', iterative_code, 1)
                iterative_code = re.sub(r'^[ ]{4}', '', iterative_code, flags=re.M)
                code = sequential_code + iterative_code

            with open("user_code.py", "w") as f:
                f.write(code)

            command = ""
            if "humble" in str(ros_version):                
                command = f"export PYTHONPATH=$PYTHONPATH:/workspace/code; python3 /RoboticsApplicationManager/manager/manager/lint/{py_lint_source}"
            else:
                command = f"export PYTHONPATH=$PYTHONPATH:/workspace/code; python3 /RoboticsApplicationManager/manager/manager/lint/{py_lint_source}"
            
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
