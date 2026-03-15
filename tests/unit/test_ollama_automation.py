import unittest
from unittest.mock import patch
from mediatamer.ai import ensure_model_exists, run_ai


class TestOllamaAutomation(unittest.TestCase):
    @patch("mediatamer.signals.ai.ollama.Client")
    def test_ensure_model_exists_library_pulls(self, mock_client_class):
        mock_client = mock_client_class.return_value
        # Simulate model missing
        mock_client.list.return_value = {"models": [{"name": "other-model"}]}
        mock_client.pull.return_value = [{"status": "downloading"}]

        ensure_model_exists("test-model", client=mock_client)

        mock_client.pull.assert_called_once_with(model="test-model", stream=True)

    @patch("mediatamer.signals.ai.ollama.Client")
    def test_ensure_model_exists_library_no_pull_if_exists(self, mock_client_class):
        mock_client = mock_client_class.return_value
        # Simulate model exists
        mock_client.list.return_value = {"models": [{"name": "test-model"}]}

        ensure_model_exists("test-model", client=mock_client)

        mock_client.pull.assert_not_called()

    @patch("mediatamer.signals.ai.requests.get")
    @patch("mediatamer.signals.ai.requests.post")
    def test_ensure_model_exists_api_pulls(self, mock_post, mock_get):
        # Simulate model missing in tags
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"models": []}

        # Mock pull response stream
        mock_post.return_value.iter_lines.return_value = [b'{"status": "success"}']

        ensure_model_exists("test-model", api_url="http://localhost:11434")

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"], {"name": "test-model"})

    @patch("mediatamer.signals.ai.ollama.Client")
    def test_run_ai_calls_ensure_model(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_client.list.return_value = {"models": [{"name": "llama3"}]}
        mock_client.chat.return_value = {"message": {"content": "Hello"}}

        res = run_ai("test prompt")

        self.assertEqual(res, "Hello")
        mock_client.list.assert_called_once()


if __name__ == "__main__":
    unittest.main()
