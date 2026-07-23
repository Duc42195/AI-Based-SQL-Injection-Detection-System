import os

from flask import Flask, request
from psycopg2.pool import ThreadedConnectionPool

app = Flask(__name__)

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "testdb"),
    "user": os.getenv("DB_USER", "testuser"),
    "password": os.getenv("DB_PASSWORD", "testpass"),
    "host": os.getenv("DB_HOST", "postgres"),
    "port": os.getenv("DB_PORT", "5432"),
}

_pool: ThreadedConnectionPool | None = None


def _get_db():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(minconn=2, maxconn=16, **DB_CONFIG)
    return _pool.getconn()


def _put_db(conn):
    global _pool
    if _pool is not None:
        _pool.putconn(conn)

_HTML_INDEX = """\
<html><body>
<h1>Vulnerable App</h1>
<ul>
<li><a href="/search?q=admin">Search users</a></li>
<li><a href="/user?id=1">View user</a></li>
<li><a href="/product?id=1">View product</a></li>
<li><a href="/profile?uid=1">View profile</a></li>
<li><a href="/order?oid=1">View order</a></li>
</ul>
</body></html>"""

_HTML_FORM = """\
<html><body>
<form action="/search" method="GET">
<input name="q" placeholder="Search...">
<button>Go</button>
</form>
</body></html>"""


@app.route("/")
def index():
    return _HTML_INDEX


@app.route("/search")
def search():
    q = request.args.get("q", "")
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT id, name, email FROM users WHERE name LIKE '%{q}%'")
    rows = cur.fetchall()
    cur.close()
    _put_db(conn)
    parts = [f"<li>{r[0]}: {r[1]} &lt;{r[2]}&gt;</li>" for r in rows]
    return f"<html><body><ul>{''.join(parts)}</ul></body></html>"


@app.route("/user")
def user():
    uid = request.args.get("id", "1")
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT id, name, email, age FROM users WHERE id = {uid}")
    rows = cur.fetchall()
    cur.close()
    _put_db(conn)
    if not rows:
        return "User not found", 404
    r = rows[0]
    return f"ID={r[0]} Name={r[1]} Email={r[2]} Age={r[3]}"


@app.route("/product")
def product():
    pid = request.args.get("id", "1")
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT id, name, price FROM products WHERE id = {pid}")
    rows = cur.fetchall()
    cur.close()
    _put_db(conn)
    if not rows:
        return "Product not found", 404
    r = rows[0]
    return f"ID={r[0]} Name={r[1]} Price=${r[2]}"


@app.route("/profile")
def profile():
    uid = request.args.get("uid", "1")
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT uid, bio, join_date FROM profiles WHERE uid = {uid}")
    rows = cur.fetchall()
    cur.close()
    _put_db(conn)
    if not rows:
        return "Profile not found", 404
    r = rows[0]
    return f"UID={r[0]} Bio={r[1]} Joined={r[2]}"


@app.route("/order")
def order():
    oid = request.args.get("oid", "1")
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT oid, uid, total FROM orders WHERE oid = {oid}")
    rows = cur.fetchall()
    cur.close()
    _put_db(conn)
    if not rows:
        return "Order not found", 404
    r = rows[0]
    return f"OID={r[0]} UID={r[1]} Total=${r[2]}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=42801, debug=True)
