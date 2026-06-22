# Idiom 3 of 3: give up on concurrency. Correct, simple — and 64 x work (~6.5 s for what
# the concurrent versions finish in ~0.2 s).
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
    time.sleep(IO_S)
    return x


chain = RunnableLambda(doc_work)
results = [chain.invoke(i) for i in range(64)]
