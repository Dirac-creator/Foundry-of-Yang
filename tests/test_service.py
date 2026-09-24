import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from foundry.service.app import create_app
from foundry.service.store import Store


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "test.sqlite3"
    app = create_app(path)
    store = app.state.store
    alice = {"Authorization": "Bearer " + store.add_user("alice", "editor")}
    bob = {"Authorization": "Bearer " + store.add_user("bob", "editor")}
    reader = {"Authorization": "Bearer " + store.add_user("reader", "reader")}
    client = TestClient(app)
    assert client.post("/api/samples", headers=alice, json={"id":"LOT-001","kind":"lot"}).status_code == 201
    assert client.post("/api/samples", headers=alice, json={"id":"WAF-001","kind":"wafer","parent_id":"LOT-001"}).status_code == 201
    return client, store, alice, bob, reader


@pytest.fixture
def record():
    return {"submission_id":"submission-001", "sample_id":"WAF-001", "process_type":"annealing", "occurred_at":"2026-09-01T10:00:00+08:00", "parameters":{"temperature":{"value":400,"unit":"°C"},"duration":{"value":30,"unit":"min"}}, "notes":"test"}


def test_auth_and_read_only(setup, record):
    client, store, alice, bob, reader = setup
    assert client.get("/api/records").status_code == 401
    assert client.get("/api/samples", headers={"Authorization":"Bearer wrong"}).status_code == 401
    assert client.post("/api/records", headers=reader, json=record).status_code == 403
    assert client.post("/api/samples", headers=reader, json={"id":"LOT-002","kind":"lot"}).status_code == 403
    assert client.get("/api/records", headers=reader).status_code == 200
    assert client.get("/api/catalog").status_code == 401


def test_shared_storage_conversion_restart_and_filter(setup, record):
    client, store, alice, bob, reader = setup
    res=client.post("/api/records", headers=alice, json=record)
    assert res.status_code == 201, res.text
    saved=res.json()
    assert saved["parameters"]["temperature"] == {"value":673.15,"unit":"K"}
    assert saved["parameters"]["duration"] == {"value":1800,"unit":"s"}
    assert saved["original_parameters"]["temperature"]["unit"] == "°C"
    assert saved["author"] == "alice"
    assert saved["occurred_at"] == "2026-09-01T02:00:00+00:00"
    assert client.get("/api/records", headers=bob).json()["total"] == 1
    restarted=TestClient(create_app(store.path))
    assert restarted.get("/api/records?sample_id=WAF-001&process_type=annealing", headers=reader).json()["total"] == 1
    assert restarted.get("/api/records?process_type=etching", headers=reader).json()["total"] == 0


@pytest.mark.parametrize("change", [
    lambda r:r.update(sample_id="UNKNOWN"),
    lambda r:r.update(occurred_at="2026-09-01T10:00:00"),
    lambda r:r.update(occurred_at="2999-01-01T00:00:00Z"),
    lambda r:r.update(process_type="unknown"),
    lambda r:r.update(parameters={}),
    lambda r:r.update(author="forged-author"),
    lambda r:r["parameters"]["temperature"].update(unit="W"),
    lambda r:r["parameters"]["temperature"].update(value=-274),
    lambda r:r["parameters"]["temperature"].update(value=True),
    lambda r:r["parameters"].update(unknown={"value":1,"unit":"s"}),
])
def test_invalid_not_saved(setup, record, change):
    client, store, alice, bob, reader = setup
    change(record)
    assert client.post("/api/records", headers=alice, json=record).status_code == 422
    assert client.get("/api/records", headers=alice).json()["total"] == 0


def test_idempotent_and_payload_conflict(setup, record):
    client, store, alice, bob, reader = setup
    first=client.post("/api/records", headers=alice, json=record).json()
    second=client.post("/api/records", headers=alice, json=record).json()
    assert first["id"] == second["id"]
    record["notes"]="different"
    assert client.post("/api/records", headers=alice, json=record).status_code == 409
    assert client.get("/api/records", headers=alice).json()["total"] == 1


def test_corrections_preserve_history(setup, record):
    client, store, alice, bob, reader = setup
    old=client.post("/api/records", headers=alice, json=record).json()
    record.update(submission_id="correction-001", supersedes_id=old["id"], notes="corrected")
    new=client.post("/api/records", headers=bob, json=record)
    assert new.status_code == 201
    assert client.get("/api/records", headers=alice).json()["total"] == 1
    assert client.get("/api/records?include_history=true", headers=alice).json()["total"] == 2
    record["submission_id"]="correction-002"
    assert client.post("/api/records", headers=alice, json=record).status_code == 409


def test_concurrent_users_and_retry(setup, record):
    client, store, alice, bob, reader = setup
    def save(i):
        with TestClient(create_app(store.path)) as c:
            body=deepcopy(record)
            body["submission_id"]="parallel-"+str(i)
            return c.post("/api/records", headers=alice if i%2 else bob, json=body)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(save, [0,1,2,3,0,1,2,3]))
    assert all(r.status_code == 201 for r in responses)
    assert client.get("/api/records", headers=reader).json()["total"] == 4


def test_backup_and_revocation(setup, record, tmp_path):
    client, store, alice, bob, reader = setup
    client.post("/api/records", headers=alice, json=record)
    destination=tmp_path/"backup.sqlite3"
    store.backup(destination)
    assert Store(destination).list_records()["total"] == 1
    with pytest.raises(ValueError):store.backup(destination)
    new=store.rotate_user("alice")
    assert client.get("/api/me", headers=alice).status_code == 401
    assert client.get("/api/me", headers={"Authorization":"Bearer "+new}).status_code == 200


def test_sample_lineage_and_static(setup):
    client, store, alice, bob, reader = setup
    assert client.post("/api/samples",headers=alice,json={"id":"DEV-001","kind":"device","parent_id":"WAF-001"}).status_code == 422
    assert client.post("/api/samples",headers=alice,json={"id":"LOT-001","kind":"lot"}).status_code == 409
    page=client.get("/")
    assert page.status_code == 200
    assert "统一录入" in page.text
    assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
    assert client.get("/assets/app.js").status_code == 200
