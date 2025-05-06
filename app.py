from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
from datetime import datetime

app = Flask(__name__)
CORS(app)

SUPABASE_URL = "https://ldjrpfsbpcfninntffoj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkanJwZnNicGNmbmlubnRmZm9qIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDY0MjcxNjYsImV4cCI6MjA2MjAwMzE2Nn0.vxPo7XXaeKPa-jDQRA2jvOJ7dvJZDHRNZB7blbONNZo"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route("/")
def home():
    return "Inventario Supabase activo"

@app.route("/buscar_producto")
def buscar_producto():
    query = request.args.get("nombre", "").lower()
    resp = supabase.table("productos").select("*").ilike("nombre", f"%{query}%").execute()
    data = resp.data if resp else []
    return jsonify(data)

@app.route("/detalle_producto")
def detalle_producto():
    referencia = request.args.get("referencia")
    if not referencia:
        return jsonify({"error": "Referencia requerida"}), 400

    res = supabase.table("productos").select("*").eq("referencia", referencia).execute()
    if not res.data:
        return jsonify({"error": "Producto no encontrado"}), 404

    producto = res.data[0]

    # Buscar movimientos
    movimientos = supabase.table("movimientos").select("*").eq("referencia", referencia).order("fecha", desc=True).execute().data
    return jsonify({
        "referencia": producto["referencia"],
        "nombre": producto["nombre"],
        "fabricante": producto["fabricante"],
        "lote": producto["lote"],
        "caducidad": producto["caducidad"],
        "movimientos": movimientos
    })

@app.route("/agregar_lote", methods=["POST"])
def agregar_lote():
    data = request.json
    data["timestamp"] = str(int(datetime.now().timestamp() * 1000))
    supabase.table("productos").insert(data).execute()
    return jsonify({"status": "ok", "mensaje": "Lote agregado"})

@app.route("/registrar_movimiento", methods=["POST"])
def registrar_movimiento():
    data = request.json
    data["fecha"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    supabase.table("movimientos").insert(data).execute()
    return jsonify({"status": "ok", "mensaje": "Movimiento registrado"})

@app.route("/registrar_qr", methods=["POST"])
def registrar_qr():
    data = request.json
    contenido = data.get("contenido", "")
    modo = data.get("modo", "entrada")
    usuario = data.get("usuario", "Desconocido")

    try:
        partes = dict(p.strip().split(":") for p in contenido.strip().split("|") if ":" in p)
        referencia = partes.get("R")
        lote = partes.get("L")
        ts = partes.get("T")
        if not referencia or not lote or not ts:
            raise ValueError("Faltan datos en QR")
    except:
        return jsonify({"status": "error", "mensaje": "Imposible leer QR"}), 400

    # Verificar timestamp duplicado
    check = supabase.table("qr_escaneados").select("*").eq("timestamp", ts).execute()
    if check.data:
        return jsonify({"status": "repetido", "color": "azul", "mensaje": "Producto escaneado anteriormente", "referencia": referencia, "nombre": "-"})

    # Buscar producto
    res = supabase.table("productos").select("*").eq("referencia", referencia).eq("lote", lote).execute()
    producto = res.data[0] if res.data else None

    if modo == "entrada":
        if not producto:
            return jsonify({"status": "error", "mensaje": "Producto no encontrado"}), 404
        supabase.table("qr_escaneados").insert({"timestamp": ts}).execute()
        supabase.table("movimientos").insert({
            "referencia": referencia,
            "lote": lote,
            "tipo": "entrada",
            "cantidad": 1,
            "usuario": usuario,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }).execute()
        return jsonify({"status": "ok", "color": "verde", "mensaje": "Nuevo producto agregado", "referencia": referencia, "nombre": producto["nombre"]})

    elif modo == "salida":
        if producto:
            supabase.table("movimientos").insert({
                "referencia": referencia,
                "lote": lote,
                "tipo": "salida",
                "cantidad": 1,
                "usuario": usuario,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }).execute()
            supabase.table("qr_escaneados").insert({"timestamp": ts}).execute()
            return jsonify({"status": "ok", "color": "rojo", "mensaje": "Producto retirado exitosamente", "referencia": referencia, "nombre": producto["nombre"]})
        else:
            return jsonify({"status": "repetido", "color": "dorado", "mensaje": "Producto ya fue retirado anteriormente", "referencia": referencia, "nombre": "-"})

    return jsonify({"status": "error", "mensaje": "Modo desconocido"}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
