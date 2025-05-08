from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
from parser_gs1 import parse_gs1_codigo as parser1
from parser_gs2 import parse_gs1_codigo as parser2
import os
import datetime

app = Flask(__name__)
CORS(app)

SUPABASE_URL = "https://ldjrpfsbpcfninntffoj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkanJwZnNicGNmbmlubnRmZm9qIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDY0MjcxNjYsImV4cCI6MjA2MjAwMzE2Nn0.vxPo7XXaeKPa-jDQRA2jvOJ7dvJZDHRNZB7blbONNZo"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Funciones auxiliares ---
def buscar_producto(ref, lote):
    result = supabase.table("productos").select("*").eq("referencia", ref).eq("lote", lote).execute()
    return result.data[0] if result.data else None

def actualizar_cantidad(ref, lote, delta):
    producto = buscar_producto(ref, lote)
    if not producto:
        return False
    nueva_cantidad = max(0, int(producto.get("cantidad", 0)) + delta)
    supabase.table("productos").update({"cantidad": nueva_cantidad}).eq("referencia", ref).eq("lote", lote).execute()
    return True

def insertar_timestamp(data):
    supabase.table("TimeStamps").insert(data).execute()

def mover_a_ts_eliminado(ts):
    supabase.table("TimeStamps").update({"ts_eliminado": True}).eq("timestamp", ts).execute()

def timestamp_existe(ts):
    result = supabase.table("TimeStamps").select("*").eq("timestamp", ts).execute()
    return result.data[0] if result.data else None

# --- Endpoint principal ---
@app.route("/registrar_qr", methods=["POST"])
def registrar_qr():
    body = request.json
    registros = body.get("registros", [])
    resultados = []
    fecha_actual = int(datetime.datetime.now().timestamp() * 1000)

    print("=== REGISTROS RECIBIDOS ===")
    print(registros)

    for r in registros:
        ref = r.get("referencia", "").strip()
        lote = r.get("lote", "").strip()
        modo = r.get("modo", "").strip()
        usuario = r.get("usuario", "").strip()
        ts = str(r.get("timestamp") or fecha_actual).strip()

        print(f"[INFO] Procesando: ref='{ref}', lote='{lote}', modo='{modo}', usuario='{usuario}', ts='{ts}'")

        if not ref or not lote or not usuario or not modo:
            print("[ERROR] Faltan datos obligatorios.")
            resultados.append({"status": "error", "mensaje": "Datos incompletos: referencia, lote, usuario o modo faltan."})
            continue

        ts_entry = timestamp_existe(ts)
        producto = buscar_producto(ref, lote)

        if modo == "entrada":
            if ts_entry:
                resultados.append({"status": "repetido", "color": "azul", "referencia": ref, "lote": lote})
            else:
                if not producto:
                    resultados.append({"status": "nuevo_producto", "referencia": ref, "lote": lote})
                insertar_timestamp({
                    "timestamp": ts,
                    "usuario": usuario,
                    "movimiento": "entrada",
                    "fecha": fecha_actual
                })
                if producto:
                    actualizar_cantidad(ref, lote, 1)
                resultados.append({"status": "ok", "color": "verde", "referencia": ref, "lote": lote})

        elif modo == "salida":
            if ts_entry:
                mover_a_ts_eliminado(ts)
                if producto:
                    actualizar_cantidad(ref, lote, -1)
                resultados.append({"status": "ok", "color": "rojo", "referencia": ref, "lote": lote})
            else:
                resultados.append({
                    "status": "extraido_previo",
                    "color": "amarillo",
                    "usuario": ts_entry.get("usuario", "-") if ts_entry else "-",
                    "fecha": ts_entry.get("fecha", "-") if ts_entry else "-"
                })

        else:
            print(f"[ERROR] Modo inválido recibido: '{modo}'")
            resultados.append({"status": "error", "mensaje": f"Modo inválido: {modo}"})

    return jsonify({"resultados": resultados})


# --- Búsqueda por referencia ---
@app.route("/buscar_referencia", methods=["GET"])
def buscar_referencia():
    ref = request.args.get("ref")
    if not ref:
        return jsonify([])
    try:
        result = supabase.table("productos").select("*").eq("referencia", ref).order("timestamp", desc=True).execute()
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Main ---
if __name__ == "__main__":
    app.run(debug=True)