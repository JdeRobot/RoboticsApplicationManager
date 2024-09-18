import tempfile
import subprocess
import os

# Read user code
code = open('user_code.py')
python_code = code.read()
code.close()

# Create temp file
code_file = tempfile.NamedTemporaryFile(delete=False)
code_file.write(python_code.encode())
code_file.seek(0)
code_file.close()

options = f"{code_file.name} --enable=similarities --disable=C0114,C0116,C0411,E0401,R0022,W0012 --max-line-length=80 --reports=y"

# Run pylint using subprocess
result = subprocess.run(['pylint'] + options.split(), capture_output=True, text=True)

# Process pylint exit
stdout = result.stdout

# Clean temp files
if os.path.exists(code_file.name):
    os.remove(code_file.name)

# Replace tmp file name with user_code
output = stdout.replace(code_file.name, "user_code") # For tmp/****
output = output.replace(code_file.name.replace("/tmp/",""), "user_code") # For ****

print(output)