import numpy as np
from sqlalchemy import create_engine, text, Index, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from sqlalchemy.dialects.postgresql import TSVECTOR
from pgvector.sqlalchemy import Vector
class B(DeclarativeBase): pass
class Chunk(B):
    __tablename__="chunk"
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]
    text: Mapped[str]
    tsv=mapped_column(TSVECTOR)
    emb=mapped_column(Vector(1536))
    __table_args__=(Index("chunk_emb","emb",postgresql_using="hnsw",postgresql_with={"m":16,"ef_construction":64},postgresql_ops={"emb":"vector_cosine_ops"}),
                    Index("chunk_tsv","tsv",postgresql_using="gin"))
e=create_engine("postgresql+psycopg://postgres:spike@localhost:54329/postgres")
with e.begin() as c: c.execute(text("create extension if not exists vector")); c.execute(text("drop table if exists chunk"))
B.metadata.create_all(e)
rng=np.random.default_rng(0)
with Session(e) as s:
    for i in range(200):
        s.add(Chunk(user_id=i%2,text=f"doc {i} Terry Smith fundsmith" if i==7 else f"doc {i} other",emb=rng.normal(size=1536).tolist()))
    s.commit()
    s.execute(text("update chunk set tsv=to_tsvector('english',text)"))
    q=rng.normal(size=1536)
    d=Chunk.emb.cosine_distance(q.tolist())
    rows=s.execute(select(Chunk.id,Chunk.user_id,d.label("d")).where(Chunk.user_id==1).order_by(d).limit(3)).all()
    print("cosine top3 (user 1 only):",rows)
    print("fts:",s.execute(select(Chunk.id).where(Chunk.tsv.op("@@")(func.websearch_to_tsquery("english","terry smith")))).all())
    print(s.execute(text("select extversion from pg_extension where extname='vector'")).scalar())
try:
    with e.begin() as c:
        c.execute(text("create table big(e vector(3072))")); c.execute(text("create index on big using hnsw (e vector_cosine_ops)"))
except Exception as ex: print("3072 hnsw:",str(ex.orig).splitlines()[0])
