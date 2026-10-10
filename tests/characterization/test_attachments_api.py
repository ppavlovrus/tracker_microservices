"""Characterization of the attachments HTTP API as it behaves today.

Expectations here were recorded from a live run, not designed. If one of them
turns red during the refactor, the refactor changed behaviour -- decide whether
that was intended before touching the assertion.
"""

from contracts import AttachmentContract, AttachmentListContract


async def test_initiate_returns_201_with_metadata_and_an_upload_url(auth_client, make_attachment):
    attachment, task = await make_attachment()

    assert attachment.task_id == task.id
    assert attachment.filename == "probe.txt"
    # The storage key is generated server-side, under the task's namespace.
    assert attachment.storage_path.startswith(f"task_{task.id}/")
    assert attachment.storage_path.endswith("probe.txt")
    # No bytes were uploaded, so there is nothing to download yet.
    assert attachment.download_url is None


async def test_the_upload_url_is_presigned_and_expires(auth_client, make_attachment):
    # The expiry is the compose default (S3_PRESIGN_EXPIRE), not a protocol
    # constant -- when the config changes, this pin changes with it.
    attachment, _ = await make_attachment(filename="expiry-probe.txt")

    assert attachment.upload_url.startswith("http")
    assert attachment.upload_expires_in == 3600


async def test_initiate_without_session_returns_401(client):
    payload = {"task_id": 1, "filename": "no-session.txt"}
    response = await client.post("/attachments", json=payload)
    assert response.status_code == 401


async def test_initiate_on_a_missing_task_returns_404(auth_client):
    payload = {"task_id": 999999, "filename": "ghost-task.txt"}

    response = await auth_client.post("/attachments", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


async def test_broken_body_422(auth_client):
    payload = {"task_id": 1}
    response = await auth_client.post("/attachments", json=payload)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any("filename" in item["loc"] for item in detail)


async def test_get_missing_attachment_returns_404(auth_client):
    response = await auth_client.get("/attachments/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Attachment not found"


async def test_get_created_attachment_adds_a_download_url(auth_client, make_attachment):
    attachment, _ = await make_attachment()

    response = await auth_client.get(f"/attachments/{attachment.id}")

    assert response.status_code == 200
    fetched = AttachmentContract.model_validate(response.json())
    assert fetched.id == attachment.id
    assert fetched.storage_path == attachment.storage_path
    # The presigned download URL appears only in the single-item answer.
    assert fetched.download_url is not None
    assert fetched.download_url.startswith("http")


async def test_list_attachments_counts_only_the_asked_task(auth_client, make_task, make_attachment):
    task = await make_task()
    first, _ = await make_attachment(task=task)
    second, _ = await make_attachment(task=task, filename="second.bin")
    elsewhere, _ = await make_attachment()

    response = await auth_client.get("/attachments", params={"task_id": task.id})

    assert response.status_code == 200
    body = AttachmentListContract.model_validate(response.json())
    assert body.total == 2
    assert {a.id for a in body.attachments} == {first.id, second.id}
    assert all(a.task_id == task.id for a in body.attachments)
    assert elsewhere.id not in {a.id for a in body.attachments}
    # List entries carry no download URL: it is a per-item presign.
    assert all(a.download_url is None for a in body.attachments)


async def test_list_attachments_requires_the_task_query_param(auth_client):
    response = await auth_client.get("/attachments")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any("task_id" in item["loc"] for item in detail)


async def test_delete_attachment_answers_204_and_then_it_is_gone(auth_client, make_attachment):
    attachment, _ = await make_attachment()

    deleted = await auth_client.delete(f"/attachments/{attachment.id}")

    assert deleted.status_code == 204
    gone = await auth_client.get(f"/attachments/{attachment.id}")
    assert gone.status_code == 404


async def test_delete_missing_attachment_returns_404(auth_client):
    response = await auth_client.delete("/attachments/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Attachment not found"
