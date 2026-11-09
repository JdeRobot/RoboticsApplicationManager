from fastapi import APIRouter, HTTPException, File
from fastapi.responses import FileResponse
import json
import os
from pydantic import BaseModel
import black

router = APIRouter(
    prefix="/format",
    tags=["formatters"],
    responses={404: {"description": "Not found"}},
)

class FileItem(BaseModel):
    content: str

@router.post("/black", response_model=FileItem)
async def format(item: FileItem):
    """
    Handle the 'code_format' event.

    Does not change the state and returns the current state.
    It uses the black formatter to format the user code.

    Parameters:
        event (Event): Has the fields code (user code).

    Returns:
        Sends the output of the black format in
            the code-format event for the frontend.
    """
    code = item.content

    # if code string is empty
    if not code:
        raise HTTPException(status_code=404, detail="User code not found")

    try:
        # Format the code with Black
        formatted_code = black.format_str(code, mode=black.Mode())
        return {"content": formatted_code}
    except Exception as e:
        raise HTTPException(status_code=404, detail="Error formating code" + str(e))

@router.post("/clang", response_model=FileItem)
async def clang(item: FileItem):
    """
    Parameters:
        event (Event): Has the fields code (user code).

    Returns:
        Sends the output of the black format in
            the code-format event for the frontend.
    """
    code = item.content

    # if code string is empty
    if not code:
        raise HTTPException(status_code=404, detail="User code not found")

    command = f"echo '{code}' | clang-format -style=file"

    try:
        # Format the code with Clang
        ret = subprocess.run(command, capture_output=True, text=True, shell=True)
        formatted_code = ret.stdout
        return {"content": formatted_code}
    except Exception as e:
        raise HTTPException(status_code=404, detail="Error formating code" + str(e))


# async def on_style_check_application(self, event):
#     """
#     Handle the 'style_check' event.

#     Does not change the state and returns the current state.

#     It uses the linter to check if the style of the code is correct, if there
#     are errors it writes them in all the consoles and raises the errors.

#     Parameters:
#         event (Event): Has the fields code (user code), exercise_id and type (bt-studio or robotics-academy) .

#     Raises:
#         Exception: with the errors found in the linter
#     """
#     # TODO: redo

#     # Extract app config
#     app_cfg = event.kwargs.get("data", {})
#     try:
#         if app_cfg["type"] == "bt-studio":
#             return
#     except Exception:
#         pass

#     exercise_id = app_cfg["exercise_id"]
#     code = app_cfg["code"]

#     # Make code backwards compatible
#     code = code.replace("from GUI import GUI", "import GUI")
#     code = code.replace("from HAL import HAL", "import HAL")

#     # Create executable app
#     errors = self.linter.evaluate_code(
#         code,
#         exercise_id,
#         self.ros_version,
#         py_lint_source="pylint_checker_style.py",
#     )

#     if errors == "":
#         errors = "No errors found"

#     self.write_to_tool_terminal(errors + "\n\n")
#     raise Exception(errors)