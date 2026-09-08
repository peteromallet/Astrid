from types import SimpleNamespace

import pytest

from astrid.sdk.client import AstridClient
from astrid.sdk.exceptions import ServiceError, ServiceNotFoundError
from astrid.sdk.remote import RemoteMedia
from astrid.sdk.workspace_client import WorkspaceClientError


@pytest.mark.parametrize("data", [b'{"results": []}', b''])
def test_public_media_reads_unscoped_artifact_bytes(data):
    calls = []
    def get_object(object_id):
        calls.append(object_id)
        return {"data": data, "status": 200, "headers": {}}
    client = AstridClient(remote=SimpleNamespace(media=RemoteMedia(SimpleNamespace(get_object=get_object))))
    assert client.media.read_bytes("artifact-id") == data
    assert calls == ["artifact-id"]


@pytest.mark.parametrize("code,error_class", [("not_found", ServiceNotFoundError), ("forbidden", ServiceError)])
def test_download_preserves_runtime_failure(code, error_class):
    def get_object(object_id):
        raise WorkspaceClientError(403, code, "artifact unavailable", {"reason": "scope"})
    media = RemoteMedia(SimpleNamespace(get_object=get_object))
    with pytest.raises(error_class) as caught:
        media.read_bytes("artifact-id")
    assert caught.value.code == code
    assert caught.value.details == {"reason": "scope"}
    assert isinstance(caught.value.__cause__, WorkspaceClientError)


@pytest.mark.parametrize("response", [{}, {"data": "not bytes"}, {"data": None}, None])
def test_download_rejects_malformed_response(response):
    media = RemoteMedia(SimpleNamespace(get_object=lambda object_id: response))
    with pytest.raises(ServiceError) as caught:
        media.read_bytes("artifact-id")
    assert caught.value.code == "protocol_error"
