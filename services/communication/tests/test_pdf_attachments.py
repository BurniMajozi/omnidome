import base64
import uuid
import pytest
from pydantic import ValidationError
from services.communication.mail_attachments import PdfAttachment
from services.communication.routes.mail import SendEmailPayload

PDF = base64.b64encode(b"%PDF-1.7\nfixture").decode()

def test_send_schema_keeps_actual_pdf_attachment():
    payload = SendEmailPayload(mailbox_id=uuid.uuid4(), to=["supplier@example.test"], subject="PO", body_text="Attached",
        attachments=[{"filename": "PO.pdf", "content_type": "application/pdf", "content": PDF}])
    assert payload.attachments[0].model_dump()["content"] == PDF

@pytest.mark.parametrize("filename", ["../PO.pdf", "dir\\PO.pdf", "PO.pdf\n", "PO.exe"])
def test_reject_unsafe_filenames(filename):
    with pytest.raises(ValidationError):
        PdfAttachment(filename=filename, content=PDF)

@pytest.mark.parametrize("content", ["bad base64", base64.b64encode(b"not a PDF").decode()])
def test_reject_non_pdf_bytes(content):
    with pytest.raises(ValidationError):
        PdfAttachment(filename="PO.pdf", content=content)

def test_no_remote_attachment_urls_or_non_pdf_content_types():
    with pytest.raises(ValidationError):
        PdfAttachment(filename="PO.pdf", content=PDF, content_type="text/html")
    with pytest.raises(ValidationError):
        SendEmailPayload(mailbox_id=uuid.uuid4(), subject="PO", body_text="Attached",
            attachments=[{"url": "http://localhost/admin", "filename": "PO.pdf"}])

def test_provider_send_forwards_attachment_bytes_without_network(monkeypatch):
    import asyncio
    import httpx
    from services.common import agentmail
    captured = []
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            captured.append(kwargs["json"])
            return httpx.Response(200, json={"message_id": "message-test"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(agentmail.httpx, "AsyncClient", FakeClient)
    attachment = PdfAttachment(filename="PO.pdf", content=PDF).model_dump()
    creds = agentmail.Creds(api_key="test-key", inbox="test@agentmail.to")
    assert asyncio.run(agentmail.send_message(["supplier@example.test"], "PO", "attached", creds=creds, attachments=[attachment])) == "message-test"
    assert captured[0]["attachments"] == [attachment]
