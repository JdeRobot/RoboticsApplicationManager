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

options = f"{code_file.name} --enable=similarities --disable=C0114,C0116"

# Run pylint using subprocess
result = subprocess.run(['pylint'] + options.split(), capture_output=True, text=True)

stdout = result.stdout

# Process pylint exit
name = os.path.basename(code_file.name)
start = stdout.find(name)
end = stdout.find('---', start)
if start != -1 and end != -1:
    result_output = stdout[start + len(name):end]
    result_output = result_output.replace(code_file.name, '')
    result_output = result_output[result_output.find('\n'):]
else:
    # Empty exit if there's no errors
    result_output = ""


# Clean temp files
if os.path.exists(code_file.name):
    os.remove(code_file.name)

print(result_output)