import hashlib
import io
import sqlite3
from zipfile import ZipFile
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from foundry.service.app import create_app
from foundry.service.store import Store
from test_service import setup, record


def make_zip():
    buffer=io.BytesIO()
    with ZipFile(buffer,"w") as archive:
        archive.writestr("gas-flow.csv", "time,O2,SF6\n0,10,5\n")
        archive.writestr("machine.log", "synthetic log")
    return buffer.getvalue()


def new_record(setup, record):
    client, store, alice, bob, reader=setup
    return client.post("/api/records",headers=alice,json=record).json()["id"]


def test_upload_download_deduplicate_shared_access_and_backup(setup,record,tmp_path):
    client,store,alice,bob,reader=setup
    rid=new_record(setup,record)
    data=make_zip();name="气体日志.xml@260706-101139.zip"
    endpoint=f"/api/records/{rid}/attachments?filename="+quote(name)
    first=client.post(endpoint,headers=alice,content=data)
    assert first.status_code==201,first.text
    item=first.json()
    assert item["filename"]==name
    assert item["size"]==len(data)
    assert item["uploaded_by"]=="alice"
    assert item["sha256"]==hashlib.sha256(data).hexdigest()
    assert "content" not in item
    assert client.post(endpoint,headers=bob,content=data).json()["id"]==item["id"]
    items=client.get(f"/api/records/{rid}/attachments",headers=reader).json()
    assert len(items)==1
    downloaded=client.get(f"/api/attachments/{item['id']}/download",headers=reader)
    assert downloaded.content==data
    assert downloaded.headers["content-type"]=="application/octet-stream"
    assert "attachment;" in downloaded.headers["content-disposition"]
    assert downloaded.headers["x-content-sha256"]==item["sha256"]
    # Same filename with new content is a separate immutable attachment.
    assert client.post(endpoint,headers=alice,content=data+b"new").json()["id"]!=item["id"]
    target=tmp_path/"attachment-backup.sqlite3";store.backup(target)
    assert Store(target).get_attachment(item["id"])["content"]==data
    restarted=TestClient(create_app(store.path))
    assert restarted.get(f"/api/attachments/{item['id']}/download",headers=bob).content==data


def test_attachment_permissions_and_missing_record(setup,record):
    client,store,alice,bob,reader=setup
    rid=new_record(setup,record)
    endpoint=f"/api/records/{rid}/attachments?filename=test.log"
    assert client.post(endpoint,content=b"log").status_code==401
    assert client.post(endpoint,headers=reader,content=b"log").status_code==403
    assert client.get(f"/api/records/{rid}/attachments").status_code==401
    assert client.get("/api/attachments/unknown/download").status_code==401
    assert client.get("/api/attachments/unknown/download",headers=reader).status_code==404
    assert client.post("/api/records/unknown/attachments?filename=x.log",headers=alice,content=b"x").status_code==404


@pytest.mark.parametrize("name", ["../x.log", "C:\\x.log", "a\r\n.log", ".", "..", "a"*241])
def test_invalid_filename_not_saved(setup,record,name):
    client,store,alice,bob,reader=setup;rid=new_record(setup,record)
    response=client.post(f"/api/records/{rid}/attachments?filename="+quote(name,safe=""),headers=alice,content=b"x")
    assert response.status_code==422
    assert store.list_attachments(rid)==[]


def test_empty_and_oversize_not_saved(setup,record):
    client,store,alice,bob,reader=setup;rid=new_record(setup,record)
    url=f"/api/records/{rid}/attachments?filename=test.zip"
    assert client.post(url,headers=alice,content=b"").status_code==422
    headers={**alice,"Content-Length":str(50*1024*1024+1)}
    assert client.post(url,headers=headers,content=b"x").status_code==413
    def chunks():
        for _ in range(51):yield b"x"*(1024*1024)
    assert client.post(url,headers=alice,content=chunks()).status_code==413
    assert store.list_attachments(rid)==[]


def test_correction_inherits_original_attachments(setup,record):
    client,store,alice,bob,reader=setup;rid=new_record(setup,record)
    item=client.post(f"/api/records/{rid}/attachments?filename=test.log",headers=alice,content=b"log").json()
    record.update(submission_id="correction-attach",supersedes_id=rid)
    new=client.post("/api/records",headers=bob,json=record).json()["id"]
    assert client.get(f"/api/records/{new}/attachments",headers=reader).json()[0]["id"]==item["id"]
    assert store.list_attachments(rid)[0]["record_id"]==rid


def test_v1_migration_preserves_data(setup,record):
    client,store,alice,bob,reader=setup;rid=new_record(setup,record)
    with store.connect() as con:
        con.execute("DROP TABLE attachments")
        con.execute("PRAGMA user_version=1")
    migrated=Store(store.path)
    assert migrated.list_records()["items"][0]["id"]==rid
    assert migrated.authenticate(alice["Authorization"].split()[1])["name"]=="alice"
    assert migrated.add_attachment(rid,"old.log",b"data","alice")["size"]==4
    with migrated.connect() as con: assert con.execute("PRAGMA user_version").fetchone()[0]==2
