-- ============================================================================
-- Skema Database — SIGIZI MBG (versi Flask/Python)
-- Optimasi menu 10 hari sekaligus per proses (bukan 1 menu per proses seperti
-- versi PHP). Kandidat gen tiap kategori dibatasi langsung lewat kolom `kategori`.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS mbg_flask CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE mbg_flask;

-- ----------------------------------------------------------------------------
-- Data Makanan (sumber utama untuk proses optimasi)
-- ----------------------------------------------------------------------------
CREATE TABLE makanan (
    id_makanan INT AUTO_INCREMENT PRIMARY KEY,
    nama VARCHAR(150) NOT NULL,
    kategori ENUM('pokok', 'lauk', 'sayur', 'buah') NOT NULL,
    berat DECIMAL(8,2) NOT NULL COMMENT 'gram',
    energi DECIMAL(8,2) NOT NULL COMMENT 'kkal',
    protein DECIMAL(8,2) NOT NULL COMMENT 'gram',
    lemak DECIMAL(8,2) NOT NULL COMMENT 'gram',
    karbo DECIMAL(8,2) NOT NULL COMMENT 'gram',
    INDEX idx_kategori (kategori),
    -- Nama+berat yang identik dianggap data duplikat (nama sama, berat beda tetap
    -- boleh -- mis. "Nasi Putih" 100g vs 150g adalah dua entri yang sah).
    UNIQUE KEY uq_nama_berat (nama, berat)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- Menu tetap (Susu) — bukan gen kromosom, ditambahkan otomatis tiap hari
-- ----------------------------------------------------------------------------
CREATE TABLE menu_tetap (
    id_menutetap INT AUTO_INCREMENT PRIMARY KEY,
    nama VARCHAR(150) NOT NULL,
    berat DECIMAL(8,2) DEFAULT NULL,
    energi DECIMAL(8,2) NOT NULL,
    protein DECIMAL(8,2) NOT NULL,
    lemak DECIMAL(8,2) NOT NULL,
    karbo DECIMAL(8,2) NOT NULL,
    is_aktif TINYINT(1) NOT NULL DEFAULT 0
) ENGINE=InnoDB;

INSERT INTO menu_tetap (nama, berat, energi, protein, lemak, karbo, is_aktif) VALUES
('Susu UHT', 200.00, 120.00, 6.00, 6.00, 10.00, 1);

-- ----------------------------------------------------------------------------
-- Target gizi makan siang (Permenkes RI No. 28 Tahun 2019 & Juknis MBG)
-- ----------------------------------------------------------------------------
CREATE TABLE target_gizi (
    id_targetgizi INT AUTO_INCREMENT PRIMARY KEY,
    energi_min DECIMAL(8,2) NOT NULL,
    energi_max DECIMAL(8,2) NOT NULL,
    protein_min DECIMAL(8,2) NOT NULL,
    protein_max DECIMAL(8,2) NOT NULL,
    lemak_min DECIMAL(8,2) NOT NULL,
    lemak_max DECIMAL(8,2) NOT NULL,
    karbo_min DECIMAL(8,2) NOT NULL,
    karbo_max DECIMAL(8,2) NOT NULL,
    sumber VARCHAR(255) NOT NULL DEFAULT 'Permenkes RI No. 28 Tahun 2019 & Juknis Program Makan Bergizi Gratis',
    is_aktif TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB;

INSERT INTO target_gizi
    (energi_min, energi_max, protein_min, protein_max, lemak_min, lemak_max, karbo_min, karbo_max)
VALUES
    (668.00, 779.00, 20.30, 23.60, 22.50, 26.30, 97.50, 113.80);

-- ----------------------------------------------------------------------------
-- Riwayat proses optimasi. Satu baris = satu kali "Jalankan Optimasi"
-- (menghasilkan SATU rencana menu 10 hari terpilih, bukan 1 menu/hari seperti
-- versi PHP -- representasi kromosom di app ini memang 10 hari sekaligus).
-- ----------------------------------------------------------------------------
CREATE TABLE hasil_optimasi (
    id_hasil INT AUTO_INCREMENT PRIMARY KEY,
    tanggal DATETIME NOT NULL,
    waktu_proses DECIMAL(10,3) DEFAULT NULL COMMENT 'detik',
    n_days INT NOT NULL DEFAULT 10,
    population_size INT NOT NULL,
    generation INT NOT NULL,
    pc DECIMAL(4,3) NOT NULL,
    pm DECIMAL(4,3) NOT NULL,
    jarak_minimum INT NOT NULL,
    penalti_pokok DECIMAL(5,2) NOT NULL,
    penalti_lauk DECIMAL(5,2) NOT NULL,
    penalti_sayur DECIMAL(5,2) NOT NULL,
    penalti_buah DECIMAL(5,2) NOT NULL,
    seed INT DEFAULT NULL,
    f1_terbaik DECIMAL(12,6) DEFAULT NULL,
    f2_terbaik DECIMAL(12,6) DEFAULT NULL,
    feasible TINYINT(1) DEFAULT NULL,
    n_fronts INT DEFAULT NULL,
    front1_size INT DEFAULT NULL,
    populasi_pareto_json JSON DEFAULT NULL COMMENT 'titik (f1,f2,feasible,rank) seluruh populasi akhir, untuk render ulang grafik Pareto',
    status ENUM('proses', 'selesai', 'gagal') NOT NULL DEFAULT 'proses',
    pesan_error TEXT DEFAULT NULL
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- Detail menu terpilih, SATU baris PER HARI dari rencana 10-hari yang dipilih
-- pada suatu hasil_optimasi (bukan seluruh solusi Pareto seperti versi PHP --
-- di app ini satu kromosom sudah mewakili seluruh 10 hari, jadi yang disimpan
-- cukup rencana yang terpilih sebagai solusi terbaik).
-- ----------------------------------------------------------------------------
CREATE TABLE detail_hasil (
    id_detail INT AUTO_INCREMENT PRIMARY KEY,
    id_hasil INT NOT NULL,
    hari TINYINT NOT NULL,
    makanan_pokok INT NOT NULL,
    lauk INT NOT NULL,
    sayur INT NOT NULL,
    buah INT NOT NULL,
    susu INT DEFAULT NULL,
    energi DECIMAL(8,2) NOT NULL,
    protein DECIMAL(8,2) NOT NULL,
    lemak DECIMAL(8,2) NOT NULL,
    karbo DECIMAL(8,2) NOT NULL,
    gizi_terpenuhi TINYINT(1) NOT NULL DEFAULT 0,
    FOREIGN KEY (id_hasil) REFERENCES hasil_optimasi(id_hasil) ON DELETE CASCADE,
    FOREIGN KEY (makanan_pokok) REFERENCES makanan(id_makanan),
    FOREIGN KEY (lauk) REFERENCES makanan(id_makanan),
    FOREIGN KEY (sayur) REFERENCES makanan(id_makanan),
    FOREIGN KEY (buah) REFERENCES makanan(id_makanan),
    FOREIGN KEY (susu) REFERENCES menu_tetap(id_menutetap),
    UNIQUE KEY uq_hasil_hari (id_hasil, hari),
    INDEX idx_id_hasil (id_hasil)
) ENGINE=InnoDB;

-- ============================================================================
-- Seed data makanan (34 item, sama seperti dataset sintetis sebelumnya, tapi
-- sekarang persisten di MySQL dan bisa di-CRUD).
-- ============================================================================
INSERT INTO makanan (nama, kategori, berat, energi, protein, lemak, karbo) VALUES
('Nasi Putih', 'pokok', 150.00, 258.00, 4.80, 0.30, 56.70),
('Nasi Merah', 'pokok', 150.00, 246.00, 5.40, 1.35, 53.10),
('Kentang Rebus', 'pokok', 150.00, 129.00, 3.00, 0.15, 29.85),
('Mie Goreng', 'pokok', 150.00, 279.00, 6.15, 9.30, 42.30),
('Nasi Liwet', 'pokok', 150.00, 267.00, 5.10, 3.60, 52.20),
('Ubi Kukus', 'pokok', 150.00, 172.50, 2.55, 0.30, 40.35),
('Nasi Uduk', 'pokok', 150.00, 300.00, 5.40, 8.55, 51.30),
('Jagung Rebus', 'pokok', 150.00, 154.50, 5.55, 1.95, 34.20),
('Ayam Goreng', 'lauk', 80.00, 231.20, 21.44, 15.20, 0.00),
('Telur Dadar', 'lauk', 60.00, 121.20, 8.10, 9.30, 1.02),
('Tempe Goreng', 'lauk', 60.00, 118.20, 9.66, 7.68, 6.42),
('Tahu Goreng', 'lauk', 60.00, 91.20, 6.24, 6.72, 2.34),
('Ikan Nila Goreng', 'lauk', 80.00, 168.80, 24.00, 7.20, 0.00),
('Rendang Daging', 'lauk', 80.00, 254.40, 17.60, 19.20, 4.00),
('Udang Goreng Tepung', 'lauk', 80.00, 196.80, 14.40, 10.40, 10.40),
('Semur Ayam', 'lauk', 80.00, 198.40, 18.40, 11.20, 5.60),
('Pepes Ikan', 'lauk', 80.00, 146.40, 20.00, 6.40, 1.60),
('Sate Ayam', 'lauk', 80.00, 220.80, 19.20, 14.40, 3.20),
('Tumis Kangkung', 'sayur', 100.00, 45.00, 2.30, 2.10, 4.50),
('Sayur Bayam Bening', 'sayur', 100.00, 36.00, 3.00, 0.60, 5.40),
('Capcay', 'sayur', 100.00, 52.00, 2.40, 2.60, 5.60),
('Sup Sayur', 'sayur', 100.00, 40.00, 1.80, 1.20, 6.20),
('Tumis Buncis', 'sayur', 100.00, 48.00, 2.20, 2.30, 5.10),
('Gado-Gado Sayur', 'sayur', 100.00, 65.00, 3.10, 3.40, 6.80),
('Sayur Asem', 'sayur', 100.00, 42.00, 1.90, 0.90, 8.10),
('Tumis Tauge', 'sayur', 100.00, 38.00, 2.60, 1.80, 3.60),
('Pisang', 'buah', 100.00, 89.00, 1.09, 0.33, 22.84),
('Semangka', 'buah', 150.00, 45.00, 0.90, 0.20, 11.30),
('Jeruk', 'buah', 100.00, 47.00, 0.94, 0.12, 11.75),
('Pepaya', 'buah', 100.00, 43.00, 0.47, 0.26, 10.82),
('Apel', 'buah', 100.00, 52.00, 0.26, 0.17, 13.81),
('Melon', 'buah', 150.00, 51.00, 1.05, 0.30, 12.30),
('Jambu Biji', 'buah', 100.00, 68.00, 2.55, 0.95, 14.32),
('Nanas', 'buah', 100.00, 50.00, 0.54, 0.12, 13.12);
