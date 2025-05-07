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
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or "<TU_CLAVE_SUPABASE>"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def buscar_producto(ref, lote):
    result = supabase.table("productos").select("*").eq("referencia", ref).eq("lote", lote).execute()
    return result.data if result.data else None

def insertar_producto(data):
    supabase.table("productos").insert(data).execute()

def eliminar_producto(ref, lote):
    supabase.table("productos").delete().eq("referencia", ref).eq("lote", lote).execute()

@app.route("/registrar_qr", methods=["POST"])
def registrar_qr():
    body = request.json
    contenido = body.get("codigo", "").strip()
    modo = body.get("modo")
    usuario = body.get("usuario")

    datos = parser1(contenido)
    if not datos.get("SMN"):
        datos = parser2(contenido)
    if not datos.get("SMN") or not datos.get("Lote"):
        return jsonify({"status": "error", "mensaje": "QR ilegible"})

    ref, lote = datos["SMN"], datos["Lote"]
    producto = buscar_producto(ref, lote)

    if modo == "entrada":
        if producto:
            return jsonify({"status": "repetido", "referencia": ref, "lote": lote})
        data = {
            "referencia": ref,
            "lote": lote,
            "timestamp": str(int(datetime.datetime.now().timestamp() * 1000)),
            "usuario": usuario,
            "nombre": "",
            "fabricante": "",
            "caducidad": ""
        }
        insertar_producto(data)
        return jsonify({"status": "ok", "referencia": ref, "lote": lote})

    elif modo == "salida":
        if producto:
            eliminar_producto(ref, lote)
            return jsonify({"status": "ok", "referencia": ref, "lote": lote})
        else:
            return jsonify({"status": "repetido", "referencia": ref, "lote": lote})

    return jsonify({"status": "error", "mensaje": "Modo inválido"})

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

if __name__ == "__main__":
    app.run(debug=True)
