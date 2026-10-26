import json

import pandas as pd

NUT_COLS = ["energi", "protein", "lemak", "karbo"]
CATEGORIES = ["pokok", "lauk", "sayur", "buah"]


# ============================================================================
# Data Makanan (dipakai mesin optimasi)
# ============================================================================
def load_makanan(conn):
    """Baca SELURUH data makanan sebagai pandas.DataFrame, dipakai
    MBGOptimizer untuk membangun ruang kandidat gen per kategori."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id_makanan, nama, kategori, berat, "
            "energi, protein, lemak, karbo FROM makanan ORDER BY kategori, nama, id_makanan"
        )
        rows = cur.fetchall()
    kolom = ["id_makanan", "nama", "kategori", "berat",
             "energi", "protein", "lemak", "karbo"]
    df = pd.DataFrame(rows, columns=kolom)
    if df.empty:
        raise ValueError(
            "Tabel `makanan` kosong (0 baris). Import data makanan terlebih "
            "dahulu (menu CRUD Data Makanan > Import CSV) sebelum menjalankan optimasi."
        )
    return df


def load_target_gizi(conn):
    """Baca baris target_gizi yang aktif."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM target_gizi WHERE is_aktif=1 ORDER BY id_targetgizi DESC LIMIT 1")
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("Belum ada target_gizi aktif di database.")
    return row


def load_susu(conn):
    """Baca menu tetap (susu) aktif -- yaitu baris dengan is_aktif=1, yang
    dipakai mesin optimasi sebagai komponen tetap tiap hari."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM menu_tetap WHERE is_aktif=1 ORDER BY id_menutetap DESC LIMIT 1")
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("Belum ada menu_tetap (susu) yang aktif di database. "
                            "Aktifkan salah satu menu tetap terlebih dahulu.")
    return row


# ============================================================================
# CRUD Menu Tetap / Susu (dipakai endpoint /api/menu-tetap)
#
# Catatan desain: menu tetap yang dipakai mesin optimasi (load_susu()) adalah
# baris dengan is_aktif=1. Hanya SATU baris yang boleh aktif dalam satu waktu
# -- mengaktifkan satu baris otomatis menonaktifkan baris lain (lihat
# set_menu_tetap_aktif()).
# ============================================================================
def list_menu_tetap(conn, q=None):
    sql = "SELECT * FROM menu_tetap WHERE 1=1"
    params = []
    if q:
        sql += " AND nama LIKE %s"
        params.append(f"%{q}%")
    sql += " ORDER BY id_menutetap ASC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def get_menu_tetap(conn, id_):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM menu_tetap WHERE id_menutetap=%s", (id_,))
        return cur.fetchone()


def create_menu_tetap(conn, data):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM menu_tetap WHERE is_aktif=1")
        ada_aktif = cur.fetchone()["n"] > 0
        # Baris pertama yang belum ada menu aktif sama sekali otomatis dijadikan
        # aktif, supaya mesin optimasi selalu punya menu tetap untuk dipakai.
        is_aktif = 0 if ada_aktif else 1
        cur.execute(
            """INSERT INTO menu_tetap (nama, berat, energi, protein, lemak, karbo, is_aktif)
               VALUES (%(nama)s,%(berat)s,%(energi)s,%(protein)s,%(lemak)s,%(karbo)s,%(is_aktif)s)""",
            dict(data, is_aktif=is_aktif),
        )
        new_id = cur.lastrowid
    conn.commit()
    return new_id


def update_menu_tetap(conn, id_, data):
    """Update data gizi/nama saja -- status aktif diubah lewat
    set_menu_tetap_aktif(), bukan lewat form edit ini."""
    data = dict(data, id_menutetap=id_)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE menu_tetap SET nama=%(nama)s, berat=%(berat)s,
               energi=%(energi)s, protein=%(protein)s, lemak=%(lemak)s, karbo=%(karbo)s
               WHERE id_menutetap=%(id_menutetap)s""",
            data,
        )
    conn.commit()


def set_menu_tetap_aktif(conn, id_):
    """Jadikan satu baris menu_tetap sebagai aktif (dipakai mesin optimasi),
    dan nonaktifkan seluruh baris lain. Mengembalikan False kalau id_ tidak
    ditemukan (tidak ada baris yang diubah)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id_menutetap FROM menu_tetap WHERE id_menutetap=%s", (id_,))
        if cur.fetchone() is None:
            return False
        cur.execute("UPDATE menu_tetap SET is_aktif=0")
        cur.execute("UPDATE menu_tetap SET is_aktif=1 WHERE id_menutetap=%s", (id_,))
    conn.commit()
    return True


def delete_menu_tetap(conn, id_):
    """Bisa melempar pymysql.err.IntegrityError kalau baris ini sudah dipakai di
    detail_hasil (FOREIGN KEY) -- ditangani di layer app.py. Menghapus baris
    yang sedang aktif ditolak lebih dulu di layer app.py supaya selalu ada
    menu tetap aktif untuk mesin optimasi."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM menu_tetap WHERE id_menutetap=%s", (id_,))
    conn.commit()


def import_menu_tetap_bulk(conn, rows):
    """Insert massal (dipakai fitur import CSV menu tetap). Tidak ada kolom unik
    (tidak seperti `nama`+`berat` pada makanan), jadi tiap baris CSV selalu
    INSERT baris baru -- bukan upsert. Mengembalikan (jumlah_sukses, daftar_pesan_gagal)."""
    sukses = 0
    gagal = []
    with conn.cursor() as cur:
        for i, row in enumerate(rows, start=2):  # baris ke-2 = data pertama setelah header
            try:
                cur.execute(
                    """INSERT INTO menu_tetap (nama, berat, energi, protein, lemak, karbo)
                       VALUES (%(nama)s,%(berat)s,%(energi)s,%(protein)s,%(lemak)s,%(karbo)s)""",
                    row,
                )
                sukses += 1
            except Exception as exc:  # noqa: BLE001
                gagal.append(f"Baris {i}: {exc}")
    conn.commit()
    return sukses, gagal


# ============================================================================
# CRUD Data Makanan (dipakai endpoint /api/makanan)
# ============================================================================
def list_makanan(conn, kategori=None, q=None):
    sql = "SELECT * FROM makanan WHERE 1=1"
    params = []
    if kategori in CATEGORIES:
        sql += " AND kategori = %s"
        params.append(kategori)
    if q:
        sql += " AND nama LIKE %s"
        params.append(f"%{q}%")
    sql += " ORDER BY id_makanan DESC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def get_makanan(conn, id_):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM makanan WHERE id_makanan=%s", (id_,))
        return cur.fetchone()


def create_makanan(conn, data):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO makanan (nama, kategori, berat, energi, protein, lemak, karbo)
               VALUES (%(nama)s,%(kategori)s,%(berat)s,%(energi)s,%(protein)s,%(lemak)s,%(karbo)s)""",
            data,
        )
        new_id = cur.lastrowid
    conn.commit()
    return new_id


def update_makanan(conn, id_, data):
    data = dict(data, id_makanan=id_)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE makanan SET nama=%(nama)s, kategori=%(kategori)s,
               berat=%(berat)s, energi=%(energi)s,
               protein=%(protein)s, lemak=%(lemak)s, karbo=%(karbo)s WHERE id_makanan=%(id_makanan)s""",
            data,
        )
    conn.commit()


def delete_makanan(conn, id_):
    """Bisa melempar pymysql.err.IntegrityError kalau makanan sudah dipakai di
    detail_hasil (FOREIGN KEY) -- ditangani di layer app.py."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM makanan WHERE id_makanan=%s", (id_,))
    conn.commit()


def import_makanan_bulk(conn, rows):
    """Upsert massal (dipakai fitur import CSV opsional). Baris dengan
    nama+berat yang sama dengan data yang sudah ada akan diperbarui
    (upsert lewat UNIQUE KEY uq_nama_berat), bukan jadi duplikat baru.
    Mengembalikan (jumlah_sukses, daftar_pesan_gagal)."""
    sukses = 0
    gagal = []
    with conn.cursor() as cur:
        for i, row in enumerate(rows, start=2):  # baris ke-2 = data pertama setelah header
            try:
                cur.execute(
                    """INSERT INTO makanan (nama, kategori, berat, energi, protein, lemak, karbo)
                       VALUES (%(nama)s,%(kategori)s,%(berat)s,%(energi)s,%(protein)s,%(lemak)s,%(karbo)s)
                       ON DUPLICATE KEY UPDATE kategori=VALUES(kategori),
                           energi=VALUES(energi), protein=VALUES(protein), lemak=VALUES(lemak), karbo=VALUES(karbo)""",
                    row,
                )
                sukses += 1
            except Exception as exc:  # noqa: BLE001
                gagal.append(f"Baris {i}: {exc}")
    conn.commit()
    return sukses, gagal


# ============================================================================
# Target Gizi
# ============================================================================
def update_target_gizi(conn, data):
    """Nonaktifkan baris lama, INSERT baris baru sebagai aktif (riwayat perubahan tetap ada)."""
    with conn.cursor() as cur:
        cur.execute("UPDATE target_gizi SET is_aktif=0")
        cur.execute(
            """INSERT INTO target_gizi
                   (energi_min, energi_max, protein_min, protein_max, lemak_min, lemak_max,
                    karbo_min, karbo_max, sumber, is_aktif)
               VALUES (%(energi_min)s,%(energi_max)s,%(protein_min)s,%(protein_max)s,
                       %(lemak_min)s,%(lemak_max)s,%(karbo_min)s,%(karbo_max)s,%(sumber)s,1)""",
            data,
        )
    conn.commit()


def list_riwayat_target_gizi(conn, limit=5):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM target_gizi ORDER BY id_targetgizi DESC LIMIT %s", (limit,))
        return cur.fetchall()


def get_riwayat_hari_terakhir(conn, k):
    """Ambil k hari TERAKHIR dari hasil_optimasi paling baru yang berstatus
    'selesai' (kalau ada), untuk dipakai sebagai 'hari semu' penyambung
    constraint jarak_minimum lintas periode (lihat MBGOptimizer.riwayat_hari
    di nsga2_core.py). Dikembalikan terurut dari hari TERLAMA ke TERBARU
    (baris terakhir = paling dekat ke periode baru). Mengembalikan [] kalau
    belum ada riwayat sama sekali (mis. ini adalah periode pertama)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id_hasil FROM hasil_optimasi WHERE status='selesai' "
            "ORDER BY id_hasil DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None:
            return []
        last_hasil_id = row["id_hasil"]
        cur.execute(
            "SELECT hari, makanan_pokok, lauk, sayur, buah FROM detail_hasil "
            "WHERE id_hasil=%s ORDER BY hari DESC LIMIT %s",
            (last_hasil_id, k),
        )
        rows = cur.fetchall()
    rows.reverse()
    return rows


# ============================================================================
# Riwayat Hasil Optimasi
# ============================================================================
def buat_hasil_optimasi(conn, params):
    """INSERT baris hasil_optimasi berstatus 'proses' SEBELUM algoritma
    dijalankan, supaya ada ID yang bisa dipakai kalau prosesnya gagal
    di tengah jalan (statusnya bisa diupdate jadi 'gagal')."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO hasil_optimasi
                   (tanggal, n_days, population_size, generation, pc, pm, jarak_minimum,
                    penalti_pokok, penalti_lauk, penalti_sayur, penalti_buah, seed, status)
               VALUES (NOW(), %(n_days)s, %(population_size)s, %(generation)s, %(pc)s, %(pm)s,
                       %(jarak_minimum)s, %(penalti_pokok)s, %(penalti_lauk)s, %(penalti_sayur)s,
                       %(penalti_buah)s, %(seed)s, 'proses')""",
            params,
        )
        hasil_id = cur.lastrowid
    conn.commit()
    return hasil_id


def simpan_hasil_optimasi(conn, hasil_id, result, id_makanan_by_name_lookup):
    """Simpan hasil sukses: update ringkasan di hasil_optimasi + insert 10
    baris detail_hasil (satu per hari) untuk menu TERBAIK yang dipilih.

    id_makanan_by_name_lookup: dict {(kategori, nama): id} untuk memetakan
    balik nama makanan hasil algoritma ke id baris `makanan` di database.
    """
    best = result["best"]
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE hasil_optimasi SET
                   waktu_proses=%s, f1_terbaik=%s, f2_terbaik=%s, feasible=%s,
                   n_fronts=%s, front1_size=%s, populasi_pareto_json=%s, status='selesai'
               WHERE id_hasil=%s""",
            (
                result["elapsed_seconds"], best["f1"], best["f2"], int(best["feasible"]),
                result["n_fronts"], result["front1_size"],
                json.dumps(result["population_points"]), hasil_id,
            ),
        )

        for hari_item in best["menu"]:
            gizi_ok = all(g["status"] == "terpenuhi" for g in hari_item["gizi"].values())
            cur.execute(
                """INSERT INTO detail_hasil
                       (id_hasil, hari, makanan_pokok, lauk, sayur, buah, susu,
                        energi, protein, lemak, karbo, gizi_terpenuhi)
                   VALUES (%s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s)""",
                (
                    hasil_id, hari_item["hari"],
                    hari_item["pokok"]["id_makanan"], hari_item["lauk"]["id_makanan"],
                    hari_item["sayur"]["id_makanan"], hari_item["buah"]["id_makanan"],
                    hari_item["minuman"]["id_menutetap"],
                    hari_item["gizi"]["energi"]["nilai"], hari_item["gizi"]["protein"]["nilai"],
                    hari_item["gizi"]["lemak"]["nilai"], hari_item["gizi"]["karbo"]["nilai"],
                    int(gizi_ok),
                ),
            )
    conn.commit()


def tandai_gagal(conn, hasil_id, pesan):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE hasil_optimasi SET status='gagal', pesan_error=%s WHERE id_hasil=%s",
            (pesan, hasil_id),
        )
    conn.commit()


def list_riwayat(conn, limit=50):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT ho.*, (SELECT COUNT(*) FROM detail_hasil dh WHERE dh.id_hasil = ho.id_hasil) AS jumlah_hari_tersimpan
               FROM hasil_optimasi ho ORDER BY ho.id_hasil DESC LIMIT %s""",
            (limit,),
        )
        return cur.fetchall()


def get_hasil_optimasi(conn, hasil_id):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM hasil_optimasi WHERE id_hasil=%s", (hasil_id,))
        row = cur.fetchone()
    if row and row.get("populasi_pareto_json"):
        # pymysql tidak otomatis decode kolom JSON jadi objek Python -- baris
        # ini yang menerjemahkannya balik supaya API mengembalikan array/objek
        # asli, bukan string JSON mentah.
        try:
            row["populasi_pareto_json"] = json.loads(row["populasi_pareto_json"])
        except (TypeError, json.JSONDecodeError):
            pass
    return row


def get_detail_hasil(conn, hasil_id):
    """Ambil 10 baris menu harian suatu hasil_optimasi, sudah di-JOIN dengan
    nama makanan supaya siap ditampilkan tanpa query tambahan."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT dh.*, mp.nama AS pokok_nama, mp.berat AS pokok_berat,
                   lk.nama AS lauk_nama, lk.berat AS lauk_berat,
                   sy.nama AS sayur_nama, sy.berat AS sayur_berat,
                   bh.nama AS buah_nama, bh.berat AS buah_berat,
                   mt.nama AS susu_nama, mt.berat AS susu_berat
            FROM detail_hasil dh
            JOIN makanan mp ON dh.makanan_pokok = mp.id_makanan
            JOIN makanan lk ON dh.lauk = lk.id_makanan
            JOIN makanan sy ON dh.sayur = sy.id_makanan
            JOIN makanan bh ON dh.buah = bh.id_makanan
            LEFT JOIN menu_tetap mt ON dh.susu = mt.id_menutetap
            WHERE dh.id_hasil = %s
            ORDER BY dh.hari ASC
            """,
            (hasil_id,),
        )
        return cur.fetchall()
