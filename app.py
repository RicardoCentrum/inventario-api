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

def init_db():
    conn = None
    try:
        conn = conectar_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS qr_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                referencia TEXT,
                lote TEXT,
                tipo TEXT,
                usuario TEXT,
                fecha TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referencia TEXT NOT NULL,
                nombre TEXT NOT NULL,
                fabricante TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS lotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER,
                lote TEXT,
                caducidad TEXT,
                cantidad INTEGER,
                FOREIGN KEY (producto_id) REFERENCES productos (id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lote_id INTEGER,
                tipo TEXT,
                cantidad INTEGER,
                usuario TEXT,
                fecha TEXT,
                FOREIGN KEY (lote_id) REFERENCES lotes (id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS qr_escaneados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT UNIQUE
            )
        """)

        conn.commit()
    finally:
        if conn:
            conn.close()

@app.route("/buscar_producto")
def buscar_producto():
    query = request.args.get("nombre", "").lower()
    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.referencia, p.nombre, p.fabricante, l.lote, l.caducidad, l.cantidad
        FROM productos p
        JOIN lotes l ON p.id = l.producto_id
        WHERE LOWER(p.nombre) LIKE ? OR LOWER(l.lote) LIKE ? OR LOWER(p.referencia) LIKE ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%"))

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
        cur.execute("INSERT INTO productos (referencia, nombre, fabricante) VALUES (?, ?, ?)",
                    (data["referencia"], data["nombre"], data["fabricante"]))
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

@app.route("/registrar_qr", methods=["POST"])
def registrar_qr():
    data = request.json
    contenido_qr = data.get("contenido", "")
    modo = data.get("modo", "entrada")
    usuario = data.get("usuario", "Desconocido")

    try:
        import string
        contenido_qr = ''.join(c for c in contenido_qr if c in string.printable and c not in '\r\n\t')
        contenido_qr = contenido_qr.strip()
        print(f"[DEBUG] QR recibido: {contenido_qr}")
        import re
        partes = dict(re.split(r":\s*", p.strip(), maxsplit=1) for p in contenido_qr.split("|"))
        referencia = partes["ID"]
        lote = partes["Lote"]
        ts = partes["TS"]
    except Exception:
        return jsonify({"status": "error", "mensaje": "Imposible leer código QR"}), 400

    conn = conectar_db()
    try:
        cur = conn.cursor()

        # Revisar si el timestamp ya fue registrado
        cur.execute("SELECT 1 FROM qr_escaneados WHERE timestamp = ?", (ts,))
        ya_registrado = cur.fetchone()
        if ya_registrado:
            cur.execute("SELECT nombre FROM productos WHERE referencia = ?", (referencia,))
            nombre = cur.fetchone()

            if modo == "entrada":
                return jsonify({
                    "status": "repetido",
                    "color": "azul",
                    "mensaje": "Producto escaneado anteriormente",
                    "referencia": referencia,
                    "nombre": nombre["nombre"] if nombre else "Desconocido"
                })
            else:
                cur.execute("""
                    SELECT usuario FROM movimientos
                    WHERE tipo = 'salida' AND lote_id IN (
                        SELECT id FROM lotes WHERE producto_id = (
                            SELECT id FROM productos WHERE referencia = ?
                        )
                    )
                    ORDER BY fecha DESC LIMIT 1
                """, (referencia,))
                usuario_prev = cur.fetchone()
                return jsonify({
                    "status": "repetido",
                    "color": "dorado",
                    "mensaje": f"Producto ya fue retirado por {usuario_prev['usuario'] if usuario_prev else 'otro usuario'}",
                    "referencia": referencia,
                    "nombre": nombre["nombre"] if nombre else "Desconocido"
                })

        # Registrar el nuevo timestamp
        cur.execute("INSERT INTO qr_escaneados (timestamp) VALUES (?)", (ts,))

        # Buscar producto
        cur.execute("SELECT id FROM productos WHERE referencia = ?", (referencia,))
        producto = cur.fetchone()
        if not producto:
            return jsonify({"status": "error", "mensaje": "Referencia no encontrada"}), 404
        producto_id = producto["id"]

        # Buscar lote
        cur.execute("SELECT id, cantidad FROM lotes WHERE producto_id = ? AND lote = ?", (producto_id, lote))
        lote_info = cur.fetchone()
        if not lote_info:
            if modo == "salida":
                return jsonify({"status": "error", "mensaje": "No puedes retirar un lote que no existe"}), 400
            # Crear nuevo lote si es entrada
            cur.execute("INSERT INTO lotes (producto_id, lote, caducidad, cantidad) VALUES (?, ?, ?, ?)",
                        (producto_id, lote, datetime.now().strftime("%Y-%m-%d"), 1))
            lote_id = cur.lastrowid
        else:
            lote_id = lote_info["id"]
            cantidad_actual = lote_info["cantidad"]
            nueva_cantidad = cantidad_actual + 1 if modo == "entrada" else max(0, cantidad_actual - 1)
            cur.execute("UPDATE lotes SET cantidad = ? WHERE id = ?", (nueva_cantidad, lote_id))

        # Registrar movimiento
        cur.execute("INSERT INTO movimientos (lote_id, tipo, cantidad, usuario, fecha) VALUES (?, ?, ?, ?, ?)",
                    (lote_id, modo, 1, usuario, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        # Registrar escaneo en el historial
        cur.execute("""
            INSERT INTO qr_log (timestamp, referencia, lote, tipo, usuario, fecha)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ts, referencia, lote, modo, usuario, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()

        # Confirmar éxito
        cur.execute("SELECT nombre FROM productos WHERE referencia = ?", (referencia,))
        nombre = cur.fetchone()
        return jsonify({
            "status": "ok",
            "color": "verde" if modo == "entrada" else "rojo",
            "mensaje": "Nuevo producto agregado" if modo == "entrada" else "Producto retirado exitosamente",
            "referencia": referencia,
            "nombre": nombre["nombre"] if nombre else "Desconocido"
        })

    finally:
        conn.close()

#cur.execute("INSERT INTO qr_escaneados (timestamp) VALUES (?)", (ts,))
#conn.commit()

        cur.execute("SELECT nombre FROM productos WHERE referencia = ?", (referencia,))
        nombre = cur.fetchone()
        conn.close()

        return jsonify({
            "status": "ok",
            "mensaje": "Nuevo producto agregado",
            "referencia": referencia,
            "nombre": nombre["nombre"] if nombre else "Desconocido"
        })

@app.route("/")
def home():
    return "API de Inventario en línea - Flask + SQLite + Render"

@app.route("/detalle_producto")
def detalle_producto():
    referencia = request.args.get("referencia")
    conn = conectar_db()
    cur = conn.cursor()

    # Buscar producto
    cur.execute("SELECT id, nombre, fabricante FROM productos WHERE referencia = ?", (referencia,))
    prod = cur.fetchone()
    if not prod:
        return jsonify({"error": "Producto no encontrado"}), 404

    producto_id = prod["id"]

    # Buscar lotes
    cur.execute("""
        SELECT lote, caducidad, cantidad
        FROM lotes
        WHERE producto_id = ?
    """, (producto_id,))
    lotes = [dict(row) for row in cur.fetchall()]

    # Buscar movimientos
    cur.execute("""
        SELECT m.usuario, m.tipo, m.fecha, l.lote, m.cantidad
        FROM movimientos m
        JOIN lotes l ON m.lote_id = l.id
        WHERE l.producto_id = ?
        ORDER BY m.fecha DESC
    """, (producto_id,))
    movimientos = [dict(row) for row in cur.fetchall()]

    conn.close()
    return jsonify({
        "referencia": referencia,
        "nombre": prod["nombre"],
        "fabricante": prod["fabricante"],
        "lotes": lotes,
        "movimientos": movimientos
    })

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=10000)