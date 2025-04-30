
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime

app = Flask(__name__)
CORS(app)

DATABASE = "inventario.db"

def conectar_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/buscar_producto")
def buscar_producto():
    query = request.args.get("nombre", "").lower()
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, p.nombre, p.fabricante, l.lote, l.caducidad, l.cantidad
        FROM productos p
        JOIN lotes l ON p.id = l.producto_id
        WHERE LOWER(p.nombre) LIKE ? OR LOWER(l.lote) LIKE ?
    """, (f"%{query}%", f"%{query}%"))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/agregar_lote", methods=["POST"])
def agregar_lote():
    data = request.json
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM productos WHERE nombre = ? AND fabricante = ?", (data["nombre"], data["fabricante"]))
    result = cur.fetchone()
    if result:
        producto_id = result["id"]
    else:
        cur.execute("INSERT INTO productos (nombre, fabricante) VALUES (?, ?)", (data["nombre"], data["fabricante"]))
        producto_id = cur.lastrowid

    cur.execute("""
        INSERT INTO lotes (producto_id, lote, caducidad, cantidad)
        VALUES (?, ?, ?, ?)
    """, (producto_id, data["lote"], data["caducidad"], data["cantidad"]))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "mensaje": "Lote agregado"})

@app.route("/registrar_movimiento", methods=["POST"])
def registrar_movimiento():
    data = request.json
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute("SELECT id, cantidad FROM lotes WHERE lote = ?", (data["lote"],))
    row = cur.fetchone()
    if not row:
        return jsonify({"status": "error", "mensaje": "Lote no encontrado"}), 404

    lote_id, cantidad_actual = row["id"], row["cantidad"]
    nueva_cantidad = cantidad_actual + data["cantidad"] if data["tipo"] == "entrada" else cantidad_actual - data["cantidad"]
    nueva_cantidad = max(nueva_cantidad, 0)

    cur.execute("UPDATE lotes SET cantidad = ? WHERE id = ?", (nueva_cantidad, lote_id))
    cur.execute("""
        INSERT INTO movimientos (lote_id, tipo, cantidad, usuario, fecha)
        VALUES (?, ?, ?, ?, ?)
    """, (lote_id, data["tipo"], data["cantidad"], data["usuario"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "mensaje": "Movimiento registrado"})

@app.route("/")
def home():
    return "API de Inventario en línea - Flask + SQLite + Render"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
