import time
import numpy as np

NUT_COLS = ["energi", "protein", "lemak", "karbo"]
CATEGORIES = ["pokok", "lauk", "sayur", "buah"]

DEFAULT_PENALTI_KATEGORI = {"pokok": 4.0, "lauk": 4.0, "sayur": 1.0, "buah": 0.5}

KATEGORI_DIBATASI_BERURUTAN = ["pokok", "lauk"]

# Jarak minimum (dalam hari) sebelum sebuah item pokok/lauk boleh muncul lagi.
# 1 = perilaku lama (hanya dilarang identik dengan hari SEBELUMNYA saja).
DEFAULT_JARAK_MINIMUM = 3

N_DAYS = 10


class MBGOptimizer:
    """Membungkus dataset (sudah dimuat dari MySQL lewat repository.py) + NSGA-II
    untuk penyusunan menu makan siang MBG 10 hari."""

    def __init__(self, df_makanan, target_gizi, susu, n_days=N_DAYS, random_seed=42,
                 riwayat_hari=None):
        """
        df_makanan  : pandas.DataFrame kolom [id_makanan, nama, kategori,
                       berat, energi, protein, lemak, karbo] -- hasil query
                       tabel `makanan` (lihat repository.load_makanan()).
        target_gizi : dict {energi_min, energi_max, protein_min, ..., karbo_max}
                       -- hasil query tabel `target_gizi` (baris aktif).
        susu        : dict {id_menutetap, nama, berat, energi, protein, lemak, karbo}
                       -- hasil query tabel `menu_tetap`.
        riwayat_hari: array (h, 4) opsional, h <= jarak_minimum -- indeks gen
                       [pokok, lauk, sayur, buah] dari h hari TERAKHIR periode
                       sebelumnya (urut dari yang terlama ke yang paling baru),
                       sudah dipetakan ke posisi index pada dataset SAAT INI
                       (lihat repository.get_riwayat_hari_terakhir() dan
                       pemetaan id_makanan->posisi di app.py). Kalau diisi,
                       constraint jarak_minimum (pengulangan pokok/lauk) dan
                       penalti f2 otomatis memperhitungkan hari-hari ini
                       sebagai "hari semu" sebelum hari ke-1 kromosom baru,
                       tanpa mengubah rumus/algoritma inti -- lihat _get_gen().
        """
        self.n_days = n_days
        self.rng = np.random.default_rng(random_seed)

        self._penalti_kategori = dict(DEFAULT_PENALTI_KATEGORI)
        self._jarak_minimum = DEFAULT_JARAK_MINIMUM

        if riwayat_hari is None:
            self.riwayat_hari = np.zeros((0, len(CATEGORIES)), dtype=np.int32)
        else:
            self.riwayat_hari = np.asarray(riwayat_hari, dtype=np.int32)

        self.sumber_dataset = "mysql"
        self.dfs = {
            cat: df_makanan[df_makanan["kategori"] == cat].reset_index(drop=True)
            for cat in CATEGORIES
        }
        kosong = [cat for cat in CATEGORIES if len(self.dfs[cat]) == 0]
        if kosong:
            raise ValueError(
                "Data makanan kosong untuk kategori: " + ", ".join(kosong) +
                ". Tambahkan minimal satu data di tiap kategori sebelum menjalankan optimasi."
            )
        self.sizes = {cat: len(self.dfs[cat]) for cat in CATEGORIES}
        self.nut = {cat: self.dfs[cat][NUT_COLS].to_numpy(dtype=float) for cat in CATEGORIES}

        self.susu = susu
        self.susu_arr = np.array([float(susu[k]) for k in NUT_COLS])

        self.target_gizi = target_gizi
        self.bb_arr = np.array([float(target_gizi[f"{k}_min"]) for k in NUT_COLS])
        self.ba_arr = np.array([float(target_gizi[f"{k}_max"]) for k in NUT_COLS])
        self.tgt_arr = (self.bb_arr + self.ba_arr) / 2.0

    # ---------------------------------------------------------- info ----
    def dataset_info(self):
        l_p, l_l, l_s, l_b = (self.sizes[c] for c in CATEGORIES)
        kombinasi_harian = l_p * l_l * l_s * l_b
        return {
            "sumber_dataset": self.sumber_dataset,
            "category_sizes": self.sizes,
            "susu": {
                "id_menutetap": int(self.susu["id_menutetap"]),
                "nama": self.susu["nama"],
                "berat": float(self.susu["berat"]) if self.susu.get("berat") is not None else None,
                **{k: float(self.susu[k]) for k in NUT_COLS},
            },
            "target_akg": {
                "batas_bawah": {k: float(self.target_gizi[f"{k}_min"]) for k in NUT_COLS},
                "batas_atas": {k: float(self.target_gizi[f"{k}_max"]) for k in NUT_COLS},
                "target_tengah": {k: round(v, 2) for k, v in
                                  zip(NUT_COLS, self.tgt_arr.tolist())},
            },
            "kombinasi_harian": kombinasi_harian,
            "ruang_solusi_eksponen": f"{kombinasi_harian:.3e}^{self.n_days}",
            "n_days": self.n_days,
            "defaults": {
                "penalti_kategori": DEFAULT_PENALTI_KATEGORI,
                "jarak_minimum": DEFAULT_JARAK_MINIMUM,
            },
        }

    # -------------------------------------------------- representasi ----
    def random_individual(self, r):
        ind = np.empty((self.n_days, len(CATEGORIES)), dtype=np.int32)
        for ci, cat in enumerate(CATEGORIES):
            ind[:, ci] = r.integers(0, self.sizes[cat], size=self.n_days)
        return ind

    def individual_to_menu(self, ind):
        nut = self.compute_daily_nutrition(ind)
        hari_list = []
        for day in range(self.n_days):
            item = {"hari": day + 1}
            for ci, cat in enumerate(CATEGORIES):
                idx = int(ind[day, ci])
                row = self.dfs[cat].iloc[idx]
                item[cat] = {
                    "id_makanan": int(row["id_makanan"]),
                    "nama": row["nama"],
                    "berat": float(row["berat"]),
                }
            item["minuman"] = {
                "id_menutetap": int(self.susu["id_menutetap"]),
                "nama": self.susu["nama"],
                "berat": float(self.susu["berat"]) if self.susu.get("berat") is not None else None,
                "fixed": True,
            }
            gizi = {}
            for i, k in enumerate(NUT_COLS):
                nilai = float(nut[day, i])
                bb, ba = float(self.bb_arr[i]), float(self.ba_arr[i])
                gizi[k] = {
                    "nilai": round(nilai, 2),
                    "batas_bawah": bb,
                    "batas_atas": ba,
                    "status": "terpenuhi" if (bb <= nilai <= ba) else "tidak_terpenuhi",
                }
            item["gizi"] = gizi
            hari_list.append(item)
        return hari_list


    # ------------------------------------------- kontinuitas periode -----
    @property
    def _h_riwayat(self):
        """Jumlah hari riwayat (periode sebelumnya) yang tersedia sebagai
        'hari semu' di depan kromosom baru."""
        return len(self.riwayat_hari)

    def _get_gen(self, ind, ci, pos):
        """Ambil nilai gen kategori `ci` pada posisi hari `pos` (0-based,
        relatif terhadap kromosom `ind` yang sedang dievaluasi). `pos` boleh
        NEGATIF -- itu berarti merujuk ke hari riwayat periode sebelumnya:
        pos=-1 -> hari terakhir periode lalu, pos=-2 -> dua hari sebelumnya,
        dst. Return None kalau `pos` di luar jangkauan data yang tersedia
        (baik kromosom saat ini maupun riwayat)."""
        if pos >= 0:
            return int(ind[pos, ci])
        h = self._h_riwayat
        idx_riwayat = h + pos  # pos=-1 -> h-1 (baris riwayat paling akhir)
        if 0 <= idx_riwayat < h:
            return int(self.riwayat_hari[idx_riwayat, ci])
        return None

    # ------------------------------------------------------- gizi -------
    def compute_daily_nutrition(self, ind):
        total = np.zeros((self.n_days, len(NUT_COLS)))
        for ci, cat in enumerate(CATEGORIES):
            total += self.nut[cat][ind[:, ci]]
        total += self.susu_arr
        return total

    # -------------------------------------------------- objektif --------
    def f1_deviasi_gizi(self, ind):
        nut = self.compute_daily_nutrition(ind)
        return float(np.abs((nut - self.tgt_arr) / self.tgt_arr).sum())

    def f2_pengulangan_menu(self, ind):
        total = 0.0
        h = self._h_riwayat
        for cat, p in self._penalti_kategori.items():
            ci = CATEGORIES.index(cat)
            last_seen = {}
            # daftarkan dulu hari-hari riwayat (posisi semu -h..-1), supaya
            # hari pertama kromosom baru "ingat" pernah disajikan di
            # periode sebelumnya -- tanpa mengubah rumus f2 itu sendiri.
            for pos in range(-h, 0):
                item = self._get_gen(ind, ci, pos)
                if item is not None:
                    last_seen[item] = pos
            for j in range(self.n_days):
                item = int(ind[j, ci])
                if item in last_seen:
                    total += p / (j - last_seen[item])
                last_seen[item] = j
        return float(total)

    # ------------------------------------------------- constraint -------
    def _pelanggaran_gizi_hari(self, nut_hari):
        total = (np.maximum(0.0, self.bb_arr - nut_hari) / self.tgt_arr +
                 np.maximum(0.0, nut_hari - self.ba_arr) / self.tgt_arr)
        return float(total.sum())

    def _pelanggaran_gizi_hari_batch(self, nut_batch):
        viol = (np.maximum(0.0, self.bb_arr - nut_batch) / self.tgt_arr +
                np.maximum(0.0, nut_batch - self.ba_arr) / self.tgt_arr)
        return viol.sum(axis=1)

    def hitung_pelanggaran_individu(self, ind):
        '''
        Constraint keberagaman: item pokok/lauk tidak boleh sama dengan hari yang sama
        di dalam jendela `self._jarak_minimum` hari sebelumnya (bukan cuma 1 hari
        sebelumnya) -- mengurangi pengulangan yang lebih luas, bukan cuma yang
        bersebelahan. Jendela ini otomatis meluas ke hari-hari riwayat periode
        sebelumnya kalau `self.riwayat_hari` diisi (lihat _get_gen()), tanpa
        mengubah rumus/logika inti constraint ini.
        '''
        nut = self.compute_daily_nutrition(ind)
        total_violation = 0.0
        for j in range(self.n_days):
            total_violation += self._pelanggaran_gizi_hari(nut[j])
        jarak = self._jarak_minimum
        for cat in KATEGORI_DIBATASI_BERURUTAN:
            ci = CATEGORIES.index(cat)
            for j in range(self.n_days):
                cur_val = int(ind[j, ci])
                for back in range(1, jarak + 1):
                    prev_val = self._get_gen(ind, ci, j - back)
                    if prev_val is None:
                        break
                    if cur_val == prev_val:
                        total_violation += 1.0
        return total_violation

    # ---------------------------------------------------- repair --------
    def repair_operator(self, ind, r, max_attempts):
        ind = ind.copy()
        jarak = self._jarak_minimum

        def bentrok(j, ci, cat):
            cur_val = ind[j, ci]
            for back in range(1, jarak + 1):
                prev_val = self._get_gen(ind, ci, j - back)
                if prev_val is None:
                    break
                if cur_val == prev_val:
                    return True
            return False

        for cat in KATEGORI_DIBATASI_BERURUTAN:
            ci = CATEGORIES.index(cat)
            for j in range(self.n_days):
                attempt = 0
                while bentrok(j, ci, cat) and attempt < max_attempts:
                    ind[j, ci] = r.integers(0, self.sizes[cat])
                    attempt += 1

        for j in range(self.n_days):
            attempt = 0
            while attempt < max_attempts:
                nut_j = sum(self.nut[cat][ind[j, ci]] for ci, cat in enumerate(CATEGORIES)) + self.susu_arr
                v_current = self._pelanggaran_gizi_hari(nut_j)
                if v_current <= 0.0:
                    break
                best_v = v_current
                best_move = None
                for ci_ubah, cat_ubah in enumerate(CATEGORIES):
                    gen_lama = ind[j, ci_ubah]
                    nut_base = nut_j - self.nut[cat_ubah][gen_lama]
                    kandidat_nut = self.nut[cat_ubah] + nut_base
                    viol_kandidat = self._pelanggaran_gizi_hari_batch(kandidat_nut)
                    viol_kandidat[gen_lama] = np.inf
                    idx_terbaik = int(np.argmin(viol_kandidat))
                    if viol_kandidat[idx_terbaik] < best_v:
                        best_v = viol_kandidat[idx_terbaik]
                        best_move = (ci_ubah, idx_terbaik)
                if best_move is None:
                    break
                ci_ubah, kandidat_baru = best_move
                ind[j, ci_ubah] = kandidat_baru
                attempt += 1
        return ind

    # ------------------------------------------------ populasi ----------
    def init_population(self, pop_size, r, max_attempts):
        pop = [self.random_individual(r) for _ in range(pop_size)]
        return [self.repair_operator(ind, r, max_attempts) for ind in pop]

    def evaluate_individual(self, ind):
        f1 = self.f1_deviasi_gizi(ind)
        f2 = self.f2_pengulangan_menu(ind)
        violation = self.hitung_pelanggaran_individu(ind)
        return {"ind": ind, "f1": f1, "f2": f2, "violation": violation,
                "feasible": violation == 0.0}

    # ------------------------------------------- operator genetik --------
    def crossover(self, p1, p2, pc, r):
        c1, c2 = p1.copy(), p2.copy()
        if r.random() < pc:
            mask = r.random(self.n_days) < 0.5
            c1[mask] = p2[mask]
            c2[mask] = p1[mask]
        return c1, c2

    def mutate(self, ind, pm, r):
        n_mut = max(1, round(pm * self.n_days)) if pm > 0 else 0
        if n_mut == 0:
            return ind
        ind = ind.copy()
        hari_termutasi = r.choice(self.n_days, size=n_mut, replace=False)
        for d in hari_termutasi:
            for ci, cat in enumerate(CATEGORIES):
                ind[d, ci] = r.integers(0, self.sizes[cat])
        return ind

    # --------------------------------------- dominance / sorting ---------
    @staticmethod
    def constrained_dominates(a, b):
        if a["feasible"] and not b["feasible"]:
            return True
        if not a["feasible"] and b["feasible"]:
            return False
        if not a["feasible"] and not b["feasible"]:
            return a["violation"] < b["violation"]
        return (a["f1"] <= b["f1"] and a["f2"] <= b["f2"]) and (a["f1"] < b["f1"] or a["f2"] < b["f2"])

    def fast_non_dominated_sort(self, evaluated_pop):
        n = len(evaluated_pop)
        S = [[] for _ in range(n)]
        n_dom = [0] * n
        fronts = [[]]
        for p in range(n):
            for q in range(n):
                if p == q:
                    continue
                if self.constrained_dominates(evaluated_pop[p], evaluated_pop[q]):
                    S[p].append(q)
                elif self.constrained_dominates(evaluated_pop[q], evaluated_pop[p]):
                    n_dom[p] += 1
            if n_dom[p] == 0:
                evaluated_pop[p]["rank"] = 0
                fronts[0].append(p)
        i = 0
        while fronts[i]:
            next_front = []
            for p in fronts[i]:
                for q in S[p]:
                    n_dom[q] -= 1
                    if n_dom[q] == 0:
                        evaluated_pop[q]["rank"] = i + 1
                        next_front.append(q)
            i += 1
            fronts.append(next_front)
        fronts.pop()
        return fronts

    @staticmethod
    def crowding_distance(evaluated_pop, front_indices):
        l = len(front_indices)
        distance = {idx: 0.0 for idx in front_indices}
        if l == 0:
            return distance
        if l <= 2:
            for idx in front_indices:
                distance[idx] = float("inf")
        else:
            for key in ["f1", "f2"]:
                sorted_idx = sorted(front_indices, key=lambda i: evaluated_pop[i][key])
                distance[sorted_idx[0]] = float("inf")
                distance[sorted_idx[-1]] = float("inf")
                vmin = evaluated_pop[sorted_idx[0]][key]
                vmax = evaluated_pop[sorted_idx[-1]][key]
                rentang = vmax - vmin
                if rentang == 0:
                    continue
                for k in range(1, l - 1):
                    v_prev = evaluated_pop[sorted_idx[k - 1]][key]
                    v_next = evaluated_pop[sorted_idx[k + 1]][key]
                    distance[sorted_idx[k]] += (v_next - v_prev) / rentang
        for idx in front_indices:
            evaluated_pop[idx]["crowding"] = distance[idx]
        return distance

    def tournament_selection(self, evaluated_pop, r):
        i, j = r.integers(0, len(evaluated_pop), size=2)
        a, b = evaluated_pop[i], evaluated_pop[j]
        if a["rank"] < b["rank"]:
            return a["ind"]
        if b["rank"] < a["rank"]:
            return b["ind"]
        return a["ind"] if a.get("crowding", 0.0) > b.get("crowding", 0.0) else b["ind"]

    # ------------------------------------------------------- main --------
    def run(self, pop_size=60, pc=0.9, pm=0.2, max_gen=60, max_attempts_repair=15,
            random_seed=None, penalti_kategori=None, jarak_minimum=None, progress_cb=None):
        # PENTING: selalu buat generator baru di sini (bukan fallback ke
        # self.rng). np.random.default_rng(None) akan memakai entropy OS
        # sehingga setiap pemanggilan run(random_seed=None) menghasilkan
        # urutan acak yang BENAR-BENAR berbeda tiap kali dipanggil -- ini
        # yang dipakai saat toggle "Aktifkan Seed" dimatikan di UI. Kalau
        # random_seed diisi angka, hasilnya tetap reproducible seperti biasa.
        r = np.random.default_rng(random_seed)
        t0 = time.time()

        # Timpa bobot penalti pengulangan (f2) & jarak minimum pengulangan (constraint
        # keberagaman) untuk run ini. Berlaku untuk seluruh siklus GA di bawah karena
        # dipakai oleh f2_pengulangan_menu / hitung_pelanggaran_individu / repair_operator.
        self._penalti_kategori = {**DEFAULT_PENALTI_KATEGORI, **(penalti_kategori or {})}
        self._jarak_minimum = max(1, int(jarak_minimum)) if jarak_minimum is not None else DEFAULT_JARAK_MINIMUM

        populasi = self.init_population(pop_size, r, max_attempts_repair)
        evaluated = [self.evaluate_individual(ind) for ind in populasi]
        fronts = self.fast_non_dominated_sort(evaluated)
        for front in fronts:
            self.crowding_distance(evaluated, front)

        log = []
        for gen in range(max_gen):
            offspring = []
            while len(offspring) < pop_size:
                p1 = self.tournament_selection(evaluated, r)
                p2 = self.tournament_selection(evaluated, r)
                c1, c2 = self.crossover(p1, p2, pc, r)
                c1 = self.repair_operator(self.mutate(c1, pm, r), r, max_attempts_repair)
                c2 = self.repair_operator(self.mutate(c2, pm, r), r, max_attempts_repair)
                offspring.append(c1)
                if len(offspring) < pop_size:
                    offspring.append(c2)

            offspring_eval = [self.evaluate_individual(ind) for ind in offspring]
            gabungan = evaluated + offspring_eval
            gabungan_fronts = self.fast_non_dominated_sort(gabungan)
            for front in gabungan_fronts:
                self.crowding_distance(gabungan, front)

            idx_terpilih = []
            for front in gabungan_fronts:
                if len(idx_terpilih) + len(front) <= pop_size:
                    idx_terpilih.extend(front)
                else:
                    sisa = pop_size - len(idx_terpilih)
                    front_urut = sorted(front, key=lambda i: -gabungan[i]["crowding"])
                    idx_terpilih.extend(front_urut[:sisa])
                    break

            evaluated = [gabungan[i] for i in idx_terpilih]
            fronts = self.fast_non_dominated_sort(evaluated)
            for front in fronts:
                self.crowding_distance(evaluated, front)

            n_feasible = sum(1 for e in evaluated if e["feasible"])
            best_f1 = min(e["f1"] for e in evaluated)
            best_f2 = min(e["f2"] for e in evaluated)
            log.append({"generasi": gen + 1, "feasible": n_feasible,
                         "pop_size": pop_size, "best_f1": round(best_f1, 4),
                         "best_f2": round(best_f2, 4)})
            if progress_cb:
                progress_cb(log[-1])

        elapsed = time.time() - t0

        # ---- Pemilihan Solusi Rekomendasi ----
        # Di antara solusi feasible, dipilih yang meminimalkan (f2, f1) secara
        # leksikografis (utamakan variasi menu / penalti pengulangan terkecil,
        # lalu deviasi gizi terkecil sebagai pemecah seri). Jika tidak ada
        # solusi feasible sama sekali, fallback ke solusi dengan pelanggaran
        # constraint paling kecil.
        kandidat_feasible = [e for e in evaluated if e["feasible"]]
        if kandidat_feasible:
            terbaik = min(kandidat_feasible, key=lambda e: (e["f2"], e["f1"]))
            fallback = False
        else:
            terbaik = min(evaluated, key=lambda e: (e["violation"], e["f2"], e["f1"]))
            fallback = True

        front1_idx = fronts[0]

        # Diagnostik: hitung pasangan hari dengan item pokok/lauk yang sama persis (di
        # SELURUH 10 hari, bukan cuma dalam jendela jarak_minimum) pada solusi terbaik,
        # supaya bisa ditampilkan ke pengguna seberapa banyak pengulangan yang tersisa.
        pengulangan_tersisa = {}
        for cat in KATEGORI_DIBATASI_BERURUTAN:
            ci = CATEGORIES.index(cat)
            col = terbaik["ind"][:, ci]
            n_pairs = sum(1 for a in range(self.n_days) for b in range(a + 1, self.n_days) if col[a] == col[b])
            pengulangan_tersisa[cat] = n_pairs

        result = {
            "elapsed_seconds": round(elapsed, 2),
            "generations_log": log,
            "n_fronts": len(fronts),
            "front1_size": len(front1_idx),
            "applied_params": {
                "penalti_kategori": self._penalti_kategori,
                "jarak_minimum": self._jarak_minimum,
            },
            "kontinuitas_periode": {
                "riwayat_hari_dipakai": self._h_riwayat,
                "keterangan": (
                    f"{self._h_riwayat} hari terakhir dari periode sebelumnya "
                    "diperhitungkan sebagai hari semu, sehingga jarak_minimum "
                    "otomatis berlaku lintas periode."
                ) if self._h_riwayat > 0 else (
                    "Tidak ada riwayat periode sebelumnya yang dipakai "
                    "(periode pertama, atau data makanan riwayat sudah berubah)."
                ),
            },
            "pengulangan_tersisa": pengulangan_tersisa,
            "population_points": [
                {"f1": round(e["f1"], 4), "f2": round(e["f2"], 4), "feasible": e["feasible"],
                 "rank": e["rank"]}
                for e in evaluated
            ],
            "front1_points": [
                {"f1": round(evaluated[i]["f1"], 4), "f2": round(evaluated[i]["f2"], 4)}
                for i in front1_idx
            ],
            "best": {
                "f1": round(terbaik["f1"], 4),
                "f2": round(terbaik["f2"], 4),
                "violation": round(terbaik["violation"], 4),
                "feasible": terbaik["feasible"],
                "fallback": fallback,
                "menu": self.individual_to_menu(terbaik["ind"]),
            },
        }
        return result
