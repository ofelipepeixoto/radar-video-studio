"""Offline unit slices of controller bodies; not HTTP integration tests.

Loading only the two functions avoids starting queues or importing providers.
The function bodies under test are compiled unchanged from production source.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


PRIVATE = "synthetic-private-script-not-for-logs"
SOURCE = Path(__file__).resolve().parents[2] / "app/controllers/v1/video.py"


def controller_slice(name):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    function.decorator_list = []
    function.returns = None
    function.args.defaults = []
    for argument in function.args.args:
        argument.annotation = None
    state = Mock()
    state.get_task.return_value = {"video_script": PRIVATE}
    logger, manager = Mock(), Mock()
    namespace = {
        "logger": logger, "sm": SimpleNamespace(state=state), "task_manager": manager,
        "utils": SimpleNamespace(get_uuid=lambda: "task-1", to_json=repr,
                                 task_dir=lambda: "/unused", get_response=lambda *args: args),
        "base": SimpleNamespace(get_task_id=lambda request: "request-1"),
        "TaskVideoRequest": type("TaskVideoRequest", (), {}),
        "tm": SimpleNamespace(start=Mock(), is_task_busy=lambda task: False),
        "os": SimpleNamespace(path=SimpleNamespace(join=lambda *args: "/unused/task-1", exists=lambda path: False)),
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(SOURCE), "exec"), namespace)
    return namespace[name], logger, state, manager


class TestTaskLogPrivacy(unittest.TestCase):
    def test_create_preserves_response_and_queue_without_logging_payload(self):
        create, logger, state, manager = controller_slice("create_task")
        body = SimpleNamespace(model_dump=lambda: {"video_script": PRIVATE})
        response = create(SimpleNamespace(), body, "audio")
        self.assertEqual(response[1]["params"]["video_script"], PRIVATE)
        state.update_task.assert_called_once_with("task-1")
        manager.add_task.assert_called_once()
        self.assertIs(manager.add_task.call_args.kwargs["params"], body)
        logger.success.assert_called_once_with("Task created: task_id=task-1, request_id=request-1, stop_at=audio")

    def test_delete_preserves_state_transition_without_logging_stored_payload(self):
        delete, logger, state, _ = controller_slice("delete_video")
        self.assertEqual(delete(SimpleNamespace(), "task-1"), (200,))
        state.delete_task.assert_called_once_with("task-1")
        logger.success.assert_called_once_with("video deleted: task_id=task-1, request_id=request-1")


if __name__ == "__main__":
    unittest.main()
