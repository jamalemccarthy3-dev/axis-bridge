# CLIENT_PARAMS: The Persona Context
import client_params_tool as tool
def get_persona_identity(user_id):
    # Supplies the 'who' to the Auditor
    return tool.load_client_identity(user_id)
