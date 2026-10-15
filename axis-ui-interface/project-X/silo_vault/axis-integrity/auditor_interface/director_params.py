# DIRECTOR_PARAMS: The Directive Context
import director_params_tool as tool
def get_execution_logic(task_id):
    # Supplies the 'how' to the Director
    return tool.fetch_exec_params(task_id)

