# Idiom 2 of 3: "use async for concurrency". The chain is async — but the work inside is
# still blocking sync code, so the event loop SERIALIZES all 64 docs (~64 x work).
# No crash, no warning: just 18x slower than intended, silently.
import asyncio
import sqlite3
import time

from langchain_core.runnables import RunnableLambda

IO_S = 0.100

conn = sqlite3.connect("docs.db")
conn.execute("CREATE TABLE IF NOT EXISTS docs (id INTEGER PRIMARY KEY, content TEXT)")


def doc_work(x):
    cur = conn.execute("INSERT INTO docs (content) VALUES (?)", ("doc%s" % x,))
    conn.execute("SELECT content FROM docs WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.commit()
    time.sleep(IO_S)  # blocking call inside an async chain == the whole batch serializes
    return x


async def adoc_work(x):
    return doc_work(x)


chain = RunnableLambda(doc_work, afunc=adoc_work)
results = asyncio.run(chain.abatch(list(range(64)), config={"max_concurrency": 64}))
