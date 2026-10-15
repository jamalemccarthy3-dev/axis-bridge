from lib.task_runner_tool import execute_in_node
from lib import _cfg


class TaskRunner:
    def __init__(self, root=None):
        self.config = _cfg.load_config("task_runner")
        self.root = root

    def run_task(self, target_node_path, payload):
        """Dispatches the payload to the specified node. -> True only when the packet was really delivered."""
        success = execute_in_node(target_node_path, payload, self.root)
        if success:
            print(f"[TaskRunner] Task successfully deployed to {target_node_path}.")
        else:
            print("[TaskRunner] Task deployment failed.")
        return success


if __name__ == "__main__":
    TaskRunner()
