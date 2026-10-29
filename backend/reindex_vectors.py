"""Offline maintenance. Stop the API before running to keep one Chroma owner."""
import os,hashlib
from sqlalchemy import select
from backend.app.db import *
from backend.app.config import RETRIEVAL,DATA
from backend.app.rag import index_version
def main():
    if RETRIEVAL!='vector':raise SystemExit('Set RETRIEVAL_PROVIDER=vector and configure embedding first.')
    init()
    with Session.begin() as db:
        docs=list(db.scalars(select(Document).where(Document.deleted_at.is_(None),Document.active_version.is_not(None))))
        jobs=[]
        for d in docs:
            old=db.get(Version,(d.id,d.active_version));latest=db.scalar(select(Version).where(Version.document_id==d.id).order_by(Version.version.desc()))
            version=latest.version+1
            db.add(Version(document_id=d.id,version=version,content_hash=old.content_hash,storage_key=old.storage_key));jobs.append((d.id,version))
    for did,version in jobs:
        index_version(did,version)
        with Session() as db:v=db.get(Version,(did,version));print(did,version,v.status)
if __name__=='__main__':main()
