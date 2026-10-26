## Struktur Proyek

```
mbg-app/
├── database/
│   └── schema.sql            -- struktur tabel + seed data
├── config/
│   └── database.ini           -- kredensial DB
├── backend/
│   ├── app.py                 -- Flask app + seluruh REST API
│   ├── db.py                  -- koneksi MySQL (baca database.ini)
│   ├── repository.py          -- SEMUA query SQL (CRUD makanan, target gizi, riwayat)
│   ├── nsga2_core.py          -- mesin NSGA-II murni (TIDAK menyentuh DB sendiri)
│   └── requirements.txt
└── frontend/
    ├── index.html              -- 4 tampilan: Optimasi/Data Makanan/Target Gizi/Riwayat
    ├── css/style.css
    └── js/app.js
```

Pemisahan `repository.py` (akses data) dari `nsga2_core.py` (algoritma) disengaja:
mesin NSGA-II menerima data yang SUDAH dimuat (`MBGOptimizer(df_makanan, target_gizi,
susu)`) lewat parameter, tidak melakukan query sendiri -- gampang dites tanpa koneksi
database, dan gampang dipindah ke sumber data lain kalau suatu saat perlu.


## API

| Method | Endpoint | Keterangan |
|---|---|---|
| GET | `/api/info` | Info dataset (ukuran kategori, target AKG, susu tetap) |
| POST | `/api/run` | Jalankan NSGA-II, hasil disimpan ke MySQL |
| GET | `/api/makanan` | List makanan (query `?kategori=` `&q=`) |
| POST | `/api/makanan` | Tambah makanan |
| PUT | `/api/makanan/<id>` | Ubah makanan |
| DELETE | `/api/makanan/<id>` | Hapus makanan (409 kalau masih dipakai riwayat) |
| POST | `/api/makanan/import` | Import CSV massal (multipart, field `file_csv`) |
| GET | `/api/target-gizi` | Target aktif + riwayat perubahan |
| PUT | `/api/target-gizi` | Update target aktif |
| GET | `/api/riwayat` | Daftar riwayat optimasi |
| GET | `/api/riwayat/<id>` | Detail satu riwayat (menu 10 hari) |



