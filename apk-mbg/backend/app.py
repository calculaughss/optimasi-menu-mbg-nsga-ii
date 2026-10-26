import csv
import io
import os

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory, send_file, g
import pymysql

import db
import repository as repo
from nsga2_core import MBGOptimizer, CATEGORIES

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")


# ============================================================================
# Koneksi database per-request (dibuka sekali, ditutup otomatis di akhir request)
# ============================================================================
def get_db():
    if "db_conn" not in g:
        g.db_conn = db.get_connection()
    return g.db_conn


@app.teardown_appcontext
def close_db(exception=None):
    conn = g.pop("db_conn", None)
    if conn is not None:
        conn.close()


def clamp(val, lo, hi, default):
    try:
        val = float(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, val))


# ============================================================================
# Frontend
# ============================================================================
@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ============================================================================
# Info dataset (dipakai untuk mengisi panel kiri saat halaman dibuka)
# ============================================================================
@app.get("/api/info")
def api_info():
    conn = get_db()
    try:
        df_makanan = repo.load_makanan(conn)
        target_gizi = repo.load_target_gizi(conn)
        susu = repo.load_susu(conn)
        optimizer = MBGOptimizer(df_makanan, target_gizi, susu)
        return jsonify(optimizer.dataset_info())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ============================================================================
# Jalankan NSGA-II
# ============================================================================
@app.post("/api/run")
def api_run():
    body = request.get_json(silent=True) or {}
    conn = get_db()

    pop_size = int(clamp(body.get("pop_size"), 10, 300, 60))
    max_gen = int(clamp(body.get("max_gen"), 5, 300, 60))
    pc = clamp(body.get("pc"), 0.0, 1.0, 0.9)
    pm = clamp(body.get("pm"), 0.0, 1.0, 0.2)

    # ---- Toggle seed: kalau dinonaktifkan, seed dipaksa None supaya
    # MBGOptimizer.run() membuat generator acak baru yang benar-benar
    # berbeda tiap kali diklik (lihat perbaikan RNG di nsga2_core.py).
    # Kalau diaktifkan tapi kolom kosong/tidak valid, fallback ke 42.
    seed_aktif = bool(body.get("seed_aktif", True))
    if seed_aktif:
        seed_raw = body.get("seed")
        try:
            seed = int(seed_raw) if seed_raw is not None and str(seed_raw).strip() != "" else 42
        except (TypeError, ValueError):
            seed = 42
    else:
        seed = None

    penalti_kategori = {
        "pokok": clamp(body.get("penalti_pokok"), 0.0, 15.0, 4.0),
        "lauk": clamp(body.get("penalti_lauk"), 0.0, 15.0, 4.0),
        "sayur": clamp(body.get("penalti_sayur"), 0.0, 15.0, 1.0),
        "buah": clamp(body.get("penalti_buah"), 0.0, 15.0, 0.5),
    }
    jarak_minimum = int(clamp(body.get("jarak_minimum"), 1, 9, 3))

    hasil_id = repo.buat_hasil_optimasi(conn, {
        "n_days": 10, "population_size": pop_size, "generation": max_gen,
        "pc": pc, "pm": pm, "jarak_minimum": jarak_minimum, "seed": seed,
        "penalti_pokok": penalti_kategori["pokok"], "penalti_lauk": penalti_kategori["lauk"],
        "penalti_sayur": penalti_kategori["sayur"], "penalti_buah": penalti_kategori["buah"],
    })

    try:
        df_makanan = repo.load_makanan(conn)
        target_gizi = repo.load_target_gizi(conn)
        susu = repo.load_susu(conn)

        # ---- Kontinuitas lintas periode: ambil hari-hari terakhir dari
        # periode SEBELUMNYA (kalau ada) dan petakan id_makanan-nya ke posisi
        # index pada dataset SAAT INI, supaya jarak_minimum otomatis berlaku
        # lintas periode tanpa mengubah rumus/logika inti algoritma (lihat
        # MBGOptimizer.riwayat_hari & _get_gen() di nsga2_core.py).
        riwayat_rows = repo.get_riwayat_hari_terakhir(conn, jarak_minimum)
        riwayat_hari = None
        riwayat_dilewati = 0
        if riwayat_rows:
            pos_map = {
                cat: {int(row["id_makanan"]): i for i, row in
                      df_makanan[df_makanan["kategori"] == cat].reset_index(drop=True).iterrows()}
                for cat in CATEGORIES
            }
            baris = []
            for row in riwayat_rows:
                try:
                    baris.append([
                        pos_map["pokok"][row["makanan_pokok"]],
                        pos_map["lauk"][row["lauk"]],
                        pos_map["sayur"][row["sayur"]],
                        pos_map["buah"][row["buah"]],
                    ])
                except KeyError:
                    # item makanan hari itu sudah dihapus/berubah dari dataset
                    # saat ini -> hari tsb dilewati dari penyambung riwayat
                    # (tidak bisa direpresentasikan sebagai index lagi).
                    riwayat_dilewati += 1
            if baris:
                riwayat_hari = np.array(baris, dtype=np.int32)

        optimizer = MBGOptimizer(df_makanan, target_gizi, susu, riwayat_hari=riwayat_hari)

        result = optimizer.run(pop_size=pop_size, pc=pc, pm=pm, max_gen=max_gen,
                                random_seed=seed, penalti_kategori=penalti_kategori,
                                jarak_minimum=jarak_minimum)
        if riwayat_dilewati:
            result["kontinuitas_periode"]["hari_dilewati"] = riwayat_dilewati

        repo.simpan_hasil_optimasi(conn, hasil_id, result, None)

        result["hasil_id"] = hasil_id
        result["params"] = {
            "pop_size": pop_size, "max_gen": max_gen, "pc": pc, "pm": pm,
            "seed_aktif": seed_aktif, "seed": seed,
        }
        return jsonify(result)

    except ValueError as e:
        repo.tandai_gagal(conn, hasil_id, str(e))
        return jsonify({"error": str(e), "hasil_id": hasil_id}), 400
    except Exception as e:  # noqa: BLE001
        repo.tandai_gagal(conn, hasil_id, f"{type(e).__name__}: {e}")
        return jsonify({"error": "Proses optimasi gagal.", "detail": str(e), "hasil_id": hasil_id}), 500


# ============================================================================
# CRUD Data Makanan
# ============================================================================
@app.get("/api/makanan")
def api_makanan_list():
    conn = get_db()
    kategori = request.args.get("kategori")
    q = request.args.get("q")
    return jsonify(repo.list_makanan(conn, kategori=kategori, q=q))


def _validate_makanan_payload(body):
    errors = []
    data = {
        "nama": (body.get("nama") or "").strip(),
        "kategori": body.get("kategori"),
        "berat": body.get("berat"),
        "energi": body.get("energi"),
        "protein": body.get("protein"),
        "lemak": body.get("lemak"),
        "karbo": body.get("karbo"),
    }
    if not data["nama"]:
        errors.append("Nama wajib diisi.")
    if data["kategori"] not in CATEGORIES:
        errors.append("Kategori tidak valid.")
    for f in ["berat", "energi", "protein", "lemak", "karbo"]:
        try:
            data[f] = float(data[f])
            if data[f] < 0:
                errors.append(f"{f} harus >= 0.")
        except (TypeError, ValueError):
            errors.append(f"{f} harus berupa angka.")
    return data, errors


@app.post("/api/makanan")
def api_makanan_create():
    data, errors = _validate_makanan_payload(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"errors": errors}), 400
    conn = get_db()
    try:
        new_id = repo.create_makanan(conn, data)
        return jsonify({"id_makanan": new_id}), 201
    except pymysql.err.IntegrityError:
        return jsonify({"errors": ["Makanan dengan nama & berat yang sama sudah ada."]}), 409


@app.put("/api/makanan/<int:id_>")
def api_makanan_update(id_):
    data, errors = _validate_makanan_payload(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"errors": errors}), 400
    conn = get_db()
    if repo.get_makanan(conn, id_) is None:
        return jsonify({"errors": ["Data tidak ditemukan."]}), 404
    try:
        repo.update_makanan(conn, id_, data)
        return jsonify({"ok": True})
    except pymysql.err.IntegrityError:
        return jsonify({"errors": ["Makanan dengan nama & berat yang sama sudah ada."]}), 409


@app.delete("/api/makanan/<int:id_>")
def api_makanan_delete(id_):
    conn = get_db()

    if repo.get_makanan(conn, id_) is None:
        return jsonify({"errors": ["Data tidak ditemukan."]}), 404

    try:
        repo.delete_makanan(conn, id_)
        return jsonify({"ok": True})
    except pymysql.err.IntegrityError:
        return jsonify({
            "errors": [
                "Makanan ini sudah pernah dipakai pada hasil optimasi sebelumnya, "
                "tidak bisa dihapus supaya riwayat tetap utuh."
            ]
        }), 409


@app.post("/api/makanan/import")
def api_makanan_import():
    if "file_csv" not in request.files:
        return jsonify({"errors": ["File CSV wajib diunggah."]}), 400

    file = request.files["file_csv"]

    try:
        text = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({
            "errors": [
                "File tidak bisa dibaca sebagai teks (pastikan format CSV UTF-8)."
            ]
        }), 400

    reader = csv.DictReader(
        io.StringIO(text),
        delimiter=",",
        skipinitialspace=True
    )

    reader.fieldnames = [
        h.strip().lower()
        for h in (reader.fieldnames or [])
    ]

    print("FIELDNAMES:", reader.fieldnames)

    wajib = {
        "nama",
        "kategori",
        "berat",
        "energi",
        "protein",
        "lemak",
        "karbo"
    }

    missing = wajib - set(reader.fieldnames)

    if missing:
        return jsonify({
            "errors": [
                f"Kolom CSV kurang: {', '.join(sorted(missing))}"
            ]
        }), 400

    rows = []

    for r in reader:
        kategori = (r.get("kategori") or "").strip().lower()

        rows.append({
            "nama": (r.get("nama") or "").strip(),
            "kategori": kategori,
            "berat": r.get("berat") or 0,
            "energi": r.get("energi") or 0,
            "protein": r.get("protein") or 0,
            "lemak": r.get("lemak") or 0,
            "karbo": r.get("karbo") or 0,
        })

    conn = get_db()

    sukses, gagal = repo.import_makanan_bulk(conn, rows)

    return jsonify({
        "sukses": sukses,
        "gagal": gagal
    })

# ============================================================================
# CRUD Menu Tetap (Susu) -- komponen fixed yang ditambahkan otomatis tiap
# hari oleh mesin optimasi (bukan gen kromosom). Baris dengan is_aktif=1 yang
# dipakai load_susu() untuk proses optimasi (lihat repository.load_susu).
# ============================================================================
@app.get("/api/menu-tetap")
def api_menu_tetap_list():
    conn = get_db()
    q = request.args.get("q")
    return jsonify(repo.list_menu_tetap(conn, q=q))


def _validate_menu_tetap_payload(body):
    errors = []
    data = {
        "nama": (body.get("nama") or "").strip(),
        "berat": body.get("berat"),
        "energi": body.get("energi"),
        "protein": body.get("protein"),
        "lemak": body.get("lemak"),
        "karbo": body.get("karbo"),
    }
    if not data["nama"]:
        errors.append("Nama wajib diisi.")
    for f in ["energi", "protein", "lemak", "karbo"]:
        try:
            data[f] = float(data[f])
            if data[f] < 0:
                errors.append(f"{f} harus >= 0.")
        except (TypeError, ValueError):
            errors.append(f"{f} harus berupa angka.")
    if data["berat"] in (None, ""):
        data["berat"] = None
    else:
        try:
            data["berat"] = float(data["berat"])
            if data["berat"] < 0:
                errors.append("berat harus >= 0.")
        except (TypeError, ValueError):
            errors.append("berat harus berupa angka.")
    return data, errors


@app.post("/api/menu-tetap")
def api_menu_tetap_create():
    data, errors = _validate_menu_tetap_payload(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"errors": errors}), 400
    conn = get_db()
    new_id = repo.create_menu_tetap(conn, data)
    return jsonify({"id_menutetap": new_id}), 201


@app.put("/api/menu-tetap/<int:id_>")
def api_menu_tetap_update(id_):
    data, errors = _validate_menu_tetap_payload(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"errors": errors}), 400
    conn = get_db()
    if repo.get_menu_tetap(conn, id_) is None:
        return jsonify({"errors": ["Data tidak ditemukan."]}), 404
    repo.update_menu_tetap(conn, id_, data)
    return jsonify({"ok": True})


@app.post("/api/menu-tetap/<int:id_>/aktifkan")
def api_menu_tetap_aktifkan(id_):
    conn = get_db()
    ok = repo.set_menu_tetap_aktif(conn, id_)
    if not ok:
        return jsonify({"errors": ["Data tidak ditemukan."]}), 404
    return jsonify({"ok": True})


@app.delete("/api/menu-tetap/<int:id_>")
def api_menu_tetap_delete(id_):
    conn = get_db()
    item = repo.get_menu_tetap(conn, id_)
    if item is not None and item.get("is_aktif"):
        return jsonify({
            "errors": ["Menu tetap ini sedang aktif dan dipakai mesin optimasi, "
                        "aktifkan menu tetap lain terlebih dahulu sebelum menghapus ini."]
        }), 409
    try:
        repo.delete_menu_tetap(conn, id_)
        return jsonify({"ok": True})
    except pymysql.err.IntegrityError:
        return jsonify({
            "errors": ["Menu tetap ini sudah pernah dipakai pada hasil optimasi sebelumnya, "
                        "tidak bisa dihapus supaya riwayat tetap utuh."]
        }), 409


@app.post("/api/menu-tetap/import")
def api_menu_tetap_import():
    if "file_csv" not in request.files:
        return jsonify({"errors": ["File CSV wajib diunggah."]}), 400
    file = request.files["file_csv"]
    try:
        text = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({"errors": ["File tidak bisa dibaca sebagai teks (pastikan format CSV UTF-8)."]}), 400

    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [h.strip().lower() for h in (reader.fieldnames or [])]
    wajib = {"nama", "energi", "protein", "lemak", "karbo"}
    missing = wajib - set(reader.fieldnames)
    if missing:
        return jsonify({"errors": [f"Kolom CSV kurang: {', '.join(sorted(missing))}"]}), 400

    rows = []
    for r in reader:
        rows.append({
            "nama": (r.get("nama") or "").strip(),
            "berat": r.get("berat") or None,
            "energi": r.get("energi") or 0,
            "protein": r.get("protein") or 0,
            "lemak": r.get("lemak") or 0,
            "karbo": r.get("karbo") or 0,
        })

    conn = get_db()
    sukses, gagal = repo.import_menu_tetap_bulk(conn, rows)
    return jsonify({"sukses": sukses, "gagal": gagal})


# ============================================================================
# Target Gizi
# ============================================================================
@app.get("/api/target-gizi")
def api_target_gizi_get():
    conn = get_db()
    return jsonify({
        "aktif": repo.load_target_gizi(conn),
        "riwayat": repo.list_riwayat_target_gizi(conn),
    })


@app.put("/api/target-gizi")
def api_target_gizi_update():
    body = request.get_json(silent=True) or {}
    errors = []
    data = {}
    for k in ["energi_min", "energi_max", "protein_min", "protein_max",
              "lemak_min", "lemak_max", "karbo_min", "karbo_max"]:
        try:
            data[k] = float(body.get(k))
            if data[k] < 0:
                errors.append(f"{k} harus >= 0.")
        except (TypeError, ValueError):
            errors.append(f"{k} tidak valid.")
    data["sumber"] = (body.get("sumber") or "").strip() or \
        "Permenkes RI No. 28 Tahun 2019 & Juknis Program Makan Bergizi Gratis"

    if not errors:
        for g_ in ["energi", "protein", "lemak", "karbo"]:
            if data[f"{g_}_min"] > data[f"{g_}_max"]:
                errors.append(f"Batas bawah {g_} tidak boleh lebih besar dari batas atas.")

    if errors:
        return jsonify({"errors": errors}), 400

    conn = get_db()
    repo.update_target_gizi(conn, data)
    return jsonify({"ok": True})


# ============================================================================
# Riwayat Optimasi
# ============================================================================
@app.get("/api/riwayat")
def api_riwayat_list():
    conn = get_db()
    return jsonify(repo.list_riwayat(conn))


@app.get("/api/riwayat/<int:hasil_id>")
def api_riwayat_detail(hasil_id):
    conn = get_db()
    run = repo.get_hasil_optimasi(conn, hasil_id)
    if run is None:
        return jsonify({"error": "Riwayat tidak ditemukan."}), 404
    detail = repo.get_detail_hasil(conn, hasil_id)
    return jsonify({"run": run, "detail": detail})


@app.get("/api/riwayat/<int:hasil_id>/export")
def api_riwayat_export(hasil_id):
    """Unduh hasil rekomendasi (rencana menu + parameter) sebagai file Excel."""
    conn = get_db()
    run = repo.get_hasil_optimasi(conn, hasil_id)
    if run is None:
        return jsonify({"error": "Riwayat tidak ditemukan."}), 404
    detail = repo.get_detail_hasil(conn, hasil_id)
    if not detail:
        return jsonify({"error": "Detail menu untuk riwayat ini belum tersedia."}), 404

    df_menu = pd.DataFrame([{
        "Hari": d["hari"],
        "Pokok": d["pokok_nama"],
        "Berat Pokok (g)": float(d["pokok_berat"]),
        "Lauk": d["lauk_nama"],
        "Berat Lauk (g)": float(d["lauk_berat"]),
        "Sayur": d["sayur_nama"],
        "Berat Sayur (g)": float(d["sayur_berat"]),
        "Buah": d["buah_nama"],
        "Berat Buah (g)": float(d["buah_berat"]),
        "Susu": d.get("susu_nama") or "Menu tetap",
        "Berat Susu (ml)": float(d["susu_berat"]) if d.get("susu_berat") is not None else None,
        "Energi (kkal)": float(d["energi"]),
        "Protein (g)": float(d["protein"]),
        "Lemak (g)": float(d["lemak"]),
        "Karbo (g)": float(d["karbo"]),
        "Gizi Terpenuhi": "Ya" if d["gizi_terpenuhi"] else "Tidak",
    } for d in detail]).sort_values("Hari")

    df_param = pd.DataFrame([
        {"Parameter": "ID Hasil", "Nilai": run["id_hasil"]},
        {"Parameter": "Tanggal", "Nilai": str(run["tanggal"])},
        {"Parameter": "Status", "Nilai": run["status"]},
        {"Parameter": "Waktu Proses (detik)", "Nilai": run.get("waktu_proses")},
        {"Parameter": "Jumlah Hari", "Nilai": run["n_days"]},
        {"Parameter": "Ukuran Populasi", "Nilai": run["population_size"]},
        {"Parameter": "Jumlah Generasi", "Nilai": run["generation"]},
        {"Parameter": "Peluang Crossover (pc)", "Nilai": float(run["pc"])},
        {"Parameter": "Peluang Mutasi (pm)", "Nilai": float(run["pm"])},
        {"Parameter": "Jarak Minimum", "Nilai": run["jarak_minimum"]},
        {"Parameter": "Penalti Pokok", "Nilai": float(run["penalti_pokok"])},
        {"Parameter": "Penalti Lauk", "Nilai": float(run["penalti_lauk"])},
        {"Parameter": "Penalti Sayur", "Nilai": float(run["penalti_sayur"])},
        {"Parameter": "Penalti Buah", "Nilai": float(run["penalti_buah"])},
        {"Parameter": "Seed", "Nilai": run["seed"] if run["seed"] is not None else "Tidak aktif (acak)"},
        {"Parameter": "f1 Terbaik (Deviasi Gizi)", "Nilai": float(run["f1_terbaik"]) if run["f1_terbaik"] is not None else None},
        {"Parameter": "f2 Terbaik (Pengulangan Menu)", "Nilai": float(run["f2_terbaik"]) if run["f2_terbaik"] is not None else None},
        {"Parameter": "Feasible", "Nilai": "Ya" if run["feasible"] else "Tidak"},
    ])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_menu.to_excel(writer, sheet_name="Rencana Menu", index=False)
        df_param.to_excel(writer, sheet_name="Parameter", index=False)
        for sheet_name, df in [("Rencana Menu", df_menu), ("Parameter", df_param)]:
            ws = writer.sheets[sheet_name]
            for i, col in enumerate(df.columns, start=1):
                lebar = max(len(str(col)), df[col].astype(str).map(len).max() if len(df) else 0) + 4
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(lebar, 45)
    buf.seek(0)

    nama_file = f"rekomendasi-menu-mbg-{hasil_id}.xlsx"
    return send_file(
        buf, as_attachment=True, download_name=nama_file,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
