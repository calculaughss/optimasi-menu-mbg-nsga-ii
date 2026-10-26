-- ============================================================================
-- Migration: hapus kolom `kode` dari tabel makanan + cegah data duplikat
-- (nama sama DAN berat sama). Jalankan ini kalau database sudah pernah
-- dibuat dari schema.sql versi lama (yang masih punya kolom kode). Kalau
-- membuat database baru dari schema.sql versi terbaru, migration ini TIDAK
-- perlu dijalankan.
--
-- CATATAN: kalau saat ini sudah ada baris makanan dengan nama+berat yang
-- identik, ALTER TABLE di bawah akan gagal (duplicate key). Bersihkan/
-- gabungkan dulu baris duplikatnya sebelum menjalankan migration ini.
-- ============================================================================
USE mbg_flask;

ALTER TABLE makanan
    DROP INDEX kode,
    DROP COLUMN kode,
    ADD UNIQUE KEY uq_nama_berat (nama, berat);
