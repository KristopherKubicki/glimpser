import unittest
from unittest.mock import MagicMock, patch

from app.utils.llm import ask_question


class TestAskQuestion(unittest.TestCase):
    @patch("app.utils.llm.request_with_retry")
    @patch("app.utils.llm.CHATGPT_KEY", "api")
    @patch("app.utils.llm.LLM_MODEL_VERSION", "gpt-x")
    def test_success(self, mock_request):
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": " Answer "}}]}
        mock_request.return_value = response

        result = ask_question("Q?", history="H")
        self.assertEqual(result, "Answer")

        call_args = mock_request.call_args.kwargs
        self.assertEqual(call_args["headers"], {"Authorization": "Bearer api"})
        payload = call_args["json"]
        self.assertEqual(payload["model"], "gpt-x")
        self.assertIn({"role": "user", "content": "H"}, payload["messages"])
        self.assertIn({"role": "user", "content": "Q?"}, payload["messages"])

    @patch("app.utils.llm.request_with_retry")
    @patch("app.utils.llm.CHATGPT_KEY", "api")
    def test_failure_exception(self, mock_request):
        mock_request.side_effect = Exception("bad")
        self.assertIsNone(ask_question("Q?"))

    @patch("app.utils.llm.request_with_retry")
    def test_missing_question(self, mock_request):
        with patch("app.utils.llm.CHATGPT_KEY", "api"):
            self.assertIsNone(ask_question(""))
            mock_request.assert_not_called()

    @patch("app.utils.llm.request_with_retry")
    def test_missing_key(self, mock_request):
        with patch("app.utils.llm.CHATGPT_KEY", None):
            self.assertIsNone(ask_question("Q?"))
            mock_request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
