-- ============================================================================
-- Migration: tambah kolom is_aktif ke tabel menu_tetap
-- Jalankan ini kalau database sudah pernah dibuat dari schema.sql versi lama
-- (tanpa kolom is_aktif). Kalau membuat database baru dari schema.sql versi
-- terbaru, migration ini TIDAK perlu dijalankan.
-- ============================================================================
USE mbg_flask;

ALTER TABLE menu_tetap
    ADD COLUMN is_aktif TINYINT(1) NOT NULL DEFAULT 0;

-- Jadikan baris dengan id terkecil sebagai aktif, supaya perilaku lama
-- (load_susu() pakai id terkecil) tidak berubah sampai admin memilih menu
-- aktif yang baru lewat UI.
UPDATE menu_tetap
SET is_aktif = 1
WHERE id_menutetap = (SELECT id_menutetap FROM (
    SELECT MIN(id_menutetap) AS id_menutetap FROM menu_tetap
) AS t);
