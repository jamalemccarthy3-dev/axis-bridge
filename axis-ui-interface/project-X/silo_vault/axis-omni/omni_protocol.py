"""omni_protocol.py - Omni's communication suite in Python (the C++ lib/omni_protocol.cpp is the old version of this).

Every interaction goes through the same three steps, in this order:
  1. Active mirroring      - say back what was understood and ask whether it is right, before anything is done
  2. Context first         - hold the input in the sandbox registry until it has been validated; nothing runs on unvalidated input
  3. Intent vs mechanics   - log the GOAL separately from the steps that will carry it out

`OmniProtocol.process_communication(text)` returns the three lines joined by newlines (the same shape the C++ version returned), and
`process(text)` returns them as a dict plus the registry state, which is what other code should use.
The camelCase names of the C++ class are kept as aliases so anything written against the old names still works.
"""
import re
import threading

MAX_INPUT = 2000          # a longer input is refused, not silently cut: the person should know their text was too long


class OmniProtocolError(ValueError):
    """The input cannot be processed (empty, not text, or too long)."""


class OmniProtocol:
    def __init__(self):
        self._lock = threading.Lock()
        self._held = {}           # sandbox registry: id -> {"input", "validated"}
        self._next_id = 1
        self.settings = {"active_mirroring": True, "context_first": True, "intent_separation": True}

    # ---- input handling ----------------------------------------------------------------------------------------------
    @staticmethod
    def _clean(text):
        if not isinstance(text, str):
            raise OmniProtocolError("the input must be text")
        t = re.sub(r"\s+", " ", text).strip()
        if not t:
            raise OmniProtocolError("the input is empty")
        if len(t) > MAX_INPUT:
            raise OmniProtocolError("the input is longer than %d characters" % MAX_INPUT)
        return t

    # ---- the three protocols -------------------------------------------------------------------------------------------
    def apply_active_mirroring(self, user_input):
        t = self._clean(user_input)
        return 'Received: "%s". Confirming alignment: Is this the correct interpretation?' % t

    def apply_context_first(self, input_text):
        """Holds the input in the sandbox registry. It stays unvalidated until validate() is called with its id."""
        t = self._clean(input_text)
        with self._lock:
            hid = self._next_id
            self._next_id += 1
            self._held[hid] = {"input": t, "validated": False}
        return "[Sandbox Workbench] Context: %s. Holding in registry until validated. (held #%d)" % (t, hid)

    def separate_intent_from_mechanics(self, input_text):
        self._clean(input_text)
        return "[Intent Log] Goal detected. Separating from execution sequence."

    # ---- the combined suite --------------------------------------------------------------------------------------------
    def process(self, user_input):
        """-> {"mirrored", "context", "intent", "held_id"}. The input is held UNVALIDATED: only validate(held_id) releases it."""
        mirrored = self.apply_active_mirroring(user_input)
        context = self.apply_context_first(user_input)
        intent = self.separate_intent_from_mechanics(user_input)
        return {"mirrored": mirrored, "context": context, "intent": intent, "held_id": self._next_id - 1}

    def process_communication(self, user_input):
        r = self.process(user_input)
        return r["mirrored"] + "\n" + r["context"] + "\n" + r["intent"]

    # ---- the registry --------------------------------------------------------------------------------------------------
    def validate(self, held_id):
        """The person confirms the interpretation: the held input becomes validated and is returned. Unknown ids are refused."""
        with self._lock:
            if held_id not in self._held:
                raise KeyError("nothing is held under #%s" % held_id)
            self._held[held_id]["validated"] = True
            return self._held[held_id]["input"]

    def reject(self, held_id):
        with self._lock:
            if held_id not in self._held:
                raise KeyError("nothing is held under #%s" % held_id)
            return self._held.pop(held_id)["input"]

    def pending(self):
        """Inputs still waiting for the person's confirmation."""
        with self._lock:
            return {k: v["input"] for k, v in self._held.items() if not v["validated"]}

    def is_validated(self, held_id):
        with self._lock:
            return bool(self._held.get(held_id, {}).get("validated"))

    # ---- the names of the C++ class -----------------------------------------------------------------------------------
    applyActiveMirroring = apply_active_mirroring
    applyContextFirst = apply_context_first
    separateIntentFromMechanics = separate_intent_from_mechanics
    processCommunication = process_communication


if __name__ == "__main__":
    import sys
    print(OmniProtocol().process_communication(" ".join(sys.argv[1:]) or "build me a landing page"))
