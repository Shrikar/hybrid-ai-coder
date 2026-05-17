from backend.executors.provider_adapters import OpenAIAdapter


def test_openai_build_input_uses_multimodal_when_images_present():
    ctx = {
        "repoPath": "/tmp/repo",
        "attachments": [
            {
                "type": "image",
                "contentType": "image/png",
                "imageBase64": "ZmFrZQ==",
            }
        ],
    }
    built = OpenAIAdapter._build_input("analyze", ctx)
    assert isinstance(built, list)
    assert built[0]["role"] == "user"
    content = built[0]["content"]
    assert any(item.get("type") == "input_image" for item in content)


def test_openai_build_input_plain_text_when_no_images():
    ctx = {"repoPath": "/tmp/repo", "attachments": []}
    built = OpenAIAdapter._build_input("hello", ctx)
    assert isinstance(built, str)
    assert "hello" in built
