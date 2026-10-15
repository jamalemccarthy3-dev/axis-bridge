# interface/controller.py
class SystemController:
    def wait_for_input(self):
        # This acts as your "button"
        cmd = input("Press ENTER to trigger Engine analysis: ")
        return True