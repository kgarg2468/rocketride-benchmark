# The CORRECT LangChain version — fast AND safe. Note what it took: the author had to KNOW
# (a) .batch uses threads, (b) sqlite connections are thread-affine, (c) therefore state must
# be created per call, not captured. None of that is suggested by the API or checked for you.
import sqlite3
import time

from langchain_core.runnables import RunnableLambda

IO_S = 0.100


def doc_work(x):
    conn = sqlite3.connect("docs.db")  # per-call state: the discipline the author must supply
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS docs (id INTEGER PRIMARY KEY, content TEXT)")
        cur = conn.execute("INSERT INTO docs (content) VALUES (?)", ("doc%s" % x,))
        conn.execute("SELECT content FROM docs WHERE id = ?", (cur.lastrowid,)).fetchone()
        conn.commit()
        time.sleep(IO_S)
    finally:
        conn.close()
    return x


chain = RunnableLambda(doc_work)
results = chain.batch(list(range(64)), config={"max_concurrency": 64})
