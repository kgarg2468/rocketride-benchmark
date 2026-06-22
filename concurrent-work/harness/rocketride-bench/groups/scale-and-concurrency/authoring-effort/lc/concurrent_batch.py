# Idiom 1 of 3 a LangChain author must choose between for "same pipeline, 64 docs".
# This one looks the most natural — and CRASHES: .batch fans the shared chain (and its
# captured sqlite connection) across worker threads -> sqlite3.ProgrammingError.
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
    time.sleep(IO_S)  # the blocking model/IO call
    return x


chain = RunnableLambda(doc_work)
results = chain.batch(list(range(64)), config={"max_concurrency": 64})
