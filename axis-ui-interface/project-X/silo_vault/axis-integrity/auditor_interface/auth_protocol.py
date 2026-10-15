# AUTH_PROTOCOL: The Gatekeeper Brain
# Purpose: Orchestrates the handshake between the requester and the system.

import auth_protocol_tool as tool


def authorize_request(token, persona_id):
    # The Brain decides if the persona has the rights to perform the action
    if tool.verify_token(token, persona_id):
        print(f"[BRAIN] Access Granted for Persona: {persona_id}")
        return True
    print(f"[BRAIN] Access DENIED for Persona: {persona_id}" + (" (locked after too many failures)" if tool.locked(persona_id) else ""))
    return False
