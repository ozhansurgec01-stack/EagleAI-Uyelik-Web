from datetime import date, datetime
import os
from calendar import monthrange
from flask import Flask, render_template, request, redirect, url_for, jsonify
from database import get_db, init_db

app = Flask(__name__)
init_db()


def kalan_gun_hesapla(bitis):
    if not bitis:
        return None

    try:
        bitis_tarihi = datetime.strptime(bitis, "%Y-%m-%d").date()
    except ValueError:
        return None

    return (bitis_tarihi - date.today()).days


def durum_hesapla(bitis):
    kalan = kalan_gun_hesapla(bitis)

    if kalan is None:
        return "Aktif"

    if kalan < 0:
        return "Süresi Doldu"
    if kalan == 0:
        return "Bugün Bitiyor"
    if kalan <= 7:
        return "Yaklaşıyor"
    return "Aktif"


def ay_ekle(tarih_metni, ay):
    tarih = datetime.strptime(tarih_metni, "%Y-%m-%d").date()

    toplam_ay = tarih.month - 1 + ay
    yil = tarih.year + toplam_ay // 12
    ay_no = toplam_ay % 12 + 1
    gun = min(tarih.day, monthrange(yil, ay_no)[1])

    return date(yil, ay_no, gun).isoformat()


@app.route("/")
def dashboard():
    db = get_db()

    arama = request.args.get("arama", "").strip()

    if arama:
        pattern = f"%{arama}%"
        uyeler = db.execute("""
            SELECT *
            FROM uyeler
            WHERE ad LIKE ?
               OR soyad LIKE ?
               OR telefon LIKE ?
            ORDER BY id DESC
        """, (pattern, pattern, pattern)).fetchall()
    else:
        uyeler = db.execute("""
            SELECT *
            FROM uyeler
            ORDER BY id DESC
        """).fetchall()

    uyeler = [
        dict(
            uye,
            durum=durum_hesapla(uye["bitis"]),
            kalan_gun=kalan_gun_hesapla(uye["bitis"])
        )
        for uye in uyeler
    ]

    toplam = len(uyeler)
    aktif = sum(u["durum"] == "Aktif" for u in uyeler)
    yaklasan = sum(u["durum"] == "Yaklaşıyor" for u in uyeler)
    dolan = sum(u["durum"] == "Süresi Doldu" for u in uyeler)
    bugun = sum(u["durum"] == "Bugün Bitiyor" for u in uyeler)
    bugun_bitenler = [u for u in uyeler if u["durum"] == "Bugün Bitiyor"]

    db.close()

    return render_template(
        "dashboard.html",
        uyeler=uyeler,
        toplam=toplam,
        aktif=aktif,
        yaklasan=yaklasan,
        dolan=dolan,
        bugun=bugun,
        bugun_bitenler=bugun_bitenler,
        arama=arama
    )


@app.route("/uye/yeni", methods=["POST"])
def uye_yeni():
    db = get_db()

    db.execute("""
        INSERT INTO uyeler
        (ad, soyad, telefon, notlar, baslangic, bitis)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        request.form.get("ad", "").strip(),
        request.form.get("soyad", "").strip(),
        request.form.get("telefon", "").strip(),
        request.form.get("notlar", "").strip(),
        request.form.get("baslangic", "").strip(),
        request.form.get("bitis", "").strip()
    ))

    db.commit()
    db.close()

    return redirect(url_for("dashboard"))


@app.route("/uye/<int:uye_id>/duzenle", methods=["POST"])
def uye_duzenle(uye_id):
    db = get_db()

    db.execute("""
        UPDATE uyeler
        SET ad = ?, soyad = ?, telefon = ?, notlar = ?, baslangic = ?, bitis = ?
        WHERE id = ?
    """, (
        request.form.get("ad", "").strip(),
        request.form.get("soyad", "").strip(),
        request.form.get("telefon", "").strip(),
        request.form.get("notlar", "").strip(),
        request.form.get("baslangic", "").strip(),
        request.form.get("bitis", "").strip(),
        uye_id
    ))

    db.commit()
    db.close()

    return redirect(url_for("dashboard"))


@app.route("/uye/<int:uye_id>/yenile", methods=["POST"])
def uye_yenile(uye_id):
    yeni_bitis = request.form.get("bitis", "").strip()

    db = get_db()
    db.execute("""
        UPDATE uyeler
        SET bitis = ?
        WHERE id = ?
    """, (yeni_bitis, uye_id))

    db.commit()
    db.close()

    return redirect(url_for("dashboard"))


@app.route("/uye/<int:uye_id>/sil", methods=["POST"])
def uye_sil(uye_id):
    db = get_db()

    db.execute("DELETE FROM odemeler WHERE uye_id = ?", (uye_id,))
    db.execute("DELETE FROM yoklamalar WHERE uye_id = ?", (uye_id,))
    db.execute("DELETE FROM uyeler WHERE id = ?", (uye_id,))

    db.commit()
    db.close()

    return redirect(url_for("dashboard"))


@app.route("/uye/<int:uye_id>/odeme", methods=["POST"])
def odeme_ekle(uye_id):
    tutar = request.form.get("tutar", "").strip()
    tarih = request.form.get("tarih", "").strip()
    aciklama = request.form.get("aciklama", "").strip()

    try:
        ay = int(request.form.get("ay_sayisi", "1"))
    except ValueError:
        ay = 1

    if ay < 1:
        ay = 1

    db = get_db()

    db.execute("""
        INSERT INTO odemeler
        (uye_id, tutar, tarih, aciklama, ay_sayisi)
        VALUES (?, ?, ?, ?, ?)
    """, (uye_id, tutar, tarih, aciklama, ay))

    uye = db.execute("""
        SELECT baslangic
        FROM uyeler
        WHERE id = ?
    """, (uye_id,)).fetchone()

    if ay > 1 and uye and uye["baslangic"]:
        try:
            yeni_bitis = ay_ekle(uye["baslangic"], ay)
            db.execute("""
                UPDATE uyeler
                SET bitis = ?
                WHERE id = ?
            """, (yeni_bitis, uye_id))
        except ValueError:
            pass

    db.commit()
    db.close()

    return redirect(url_for("dashboard"))


@app.route("/odeme/<int:odeme_id>/duzenle", methods=["POST"])
def odeme_duzenle(odeme_id):
    tutar = request.form.get("tutar", "").strip()
    tarih = request.form.get("tarih", "").strip()
    aciklama = request.form.get("aciklama", "").strip()

    try:
        ay = int(request.form.get("ay_sayisi", "1"))
    except ValueError:
        ay = 1

    if ay < 1:
        ay = 1

    db = get_db()

    odeme = db.execute("""
        SELECT uye_id
        FROM odemeler
        WHERE id = ?
    """, (odeme_id,)).fetchone()

    if not odeme:
        db.close()
        return redirect(url_for("odemeler_sayfasi"))

    db.execute("""
        UPDATE odemeler
        SET tutar = ?,
            tarih = ?,
            aciklama = ?,
            ay_sayisi = ?
        WHERE id = ?
    """, (tutar, tarih, aciklama, ay, odeme_id))

    db.commit()
    db.close()

    return redirect(url_for("odemeler_sayfasi"))


@app.route("/program")
def program_sayfasi():
    db = get_db()
    gunler = [
        "Pazartesi",
        "Salı",
        "Çarşamba",
        "Perşembe",
        "Cuma",
        "Cumartesi",
        "Pazar"
    ]

    programlar = db.execute("""
        SELECT *
        FROM programlar
        ORDER BY
            CASE gun
                WHEN 'Pazartesi' THEN 1
                WHEN 'Salı' THEN 2
                WHEN 'Çarşamba' THEN 3
                WHEN 'Perşembe' THEN 4
                WHEN 'Cuma' THEN 5
                WHEN 'Cumartesi' THEN 6
                WHEN 'Pazar' THEN 7
                ELSE 8
            END,
            baslangic_saati
    """).fetchall()

    db.close()

    gun_programlari = {
        gun: [dict(p) for p in programlar if p["gun"] == gun]
        for gun in gunler
    }

    return render_template(
        "program.html",
        gunler=gunler,
        gun_programlari=gun_programlari,
        sayfa="program"
    )


@app.route("/program/ders-ekle", methods=["POST"])
def program_ders_ekle():
    ders_adi = request.form.get("ders_adi", "").strip()
    gun = request.form.get("gun", "").strip()
    baslangic_saati = request.form.get("baslangic_saati", "").strip()
    sure_dakika = request.form.get("sure_dakika", "").strip()
    egitmen = request.form.get("egitmen", "").strip()

    gunler = {
        "Pazartesi",
        "Salı",
        "Çarşamba",
        "Perşembe",
        "Cuma",
        "Cumartesi",
        "Pazar"
    }

    try:
        sure = int(sure_dakika)
    except ValueError:
        return redirect(url_for("program_sayfasi"))

    if (
        not ders_adi
        or gun not in gunler
        or not baslangic_saati
        or sure <= 0
        or not egitmen
    ):
        return redirect(url_for("program_sayfasi"))

    db = get_db()
    db.execute("""
        INSERT INTO programlar
        (gun, ders_adi, baslangic_saati, sure_dakika, egitmen)
        VALUES (?, ?, ?, ?, ?)
    """, (
        gun,
        ders_adi,
        baslangic_saati,
        sure,
        egitmen
    ))
    db.commit()
    db.close()

    return redirect(url_for("program_sayfasi"))


@app.route("/uyeler")
def uyeler_sayfasi():
    db = get_db()

    arama = request.args.get("arama", "").strip()

    try:
        secili_uye_id = int(request.args.get("uye_id", "0"))
    except ValueError:
        secili_uye_id = 0

    if arama:
        pattern = f"%{arama}%"
        uyeler = db.execute("""
            SELECT *
            FROM uyeler
            WHERE ad LIKE ?
               OR soyad LIKE ?
               OR telefon LIKE ?
            ORDER BY id DESC
        """, (pattern, pattern, pattern)).fetchall()
    else:
        uyeler = db.execute("""
            SELECT *
            FROM uyeler
            ORDER BY id DESC
        """).fetchall()

    uyeler = [
        dict(
            uye,
            durum=durum_hesapla(uye["bitis"]),
            kalan_gun=kalan_gun_hesapla(uye["bitis"])
        )
        for uye in uyeler
    ]

    db.close()

    return render_template(
        "dashboard.html",
        uyeler=uyeler,
        toplam=len(uyeler),
        aktif=sum(u["durum"] == "Aktif" for u in uyeler),
        yaklasan=sum(u["durum"] == "Yaklaşıyor" for u in uyeler),
        dolan=sum(u["durum"] == "Süresi Doldu" for u in uyeler),
        bugun=sum(u["durum"] == "Bugün Bitiyor" for u in uyeler),
        bugun_bitenler=[u for u in uyeler if u["durum"] == "Bugün Bitiyor"],
        arama=arama,
        secili_uye_id=secili_uye_id,
        sayfa="uyeler"
    )



@app.route("/odeme/<int:odeme_id>/sil", methods=["POST"])
def odeme_sil(odeme_id):
    db = get_db()
    db.execute("""
        DELETE FROM odemeler
        WHERE id = ?
    """, (odeme_id,))
    db.commit()
    db.close()
    return redirect(url_for("odemeler_sayfasi"))


@app.route("/gider/ekle", methods=["POST"])
def gider_ekle():
    ad = request.form.get("ad", "").strip()
    tutar = request.form.get("tutar", "").strip()
    tarih = request.form.get("tarih", "").strip()
    aciklama = request.form.get("aciklama", "").strip()

    if not ad or not tutar:
        return redirect(url_for("odemeler_sayfasi"))

    db = get_db()
    db.execute("""
        INSERT INTO giderler
        (ad, tutar, tarih, aciklama)
        VALUES (?, ?, ?, ?)
    """, (ad, tutar, tarih, aciklama))
    db.commit()
    db.close()
    return redirect(url_for("odemeler_sayfasi"))


@app.route("/gider/<int:gider_id>/sil", methods=["POST"])
def gider_sil(gider_id):
    db = get_db()
    db.execute("""
        DELETE FROM giderler
        WHERE id = ?
    """, (gider_id,))
    db.commit()
    db.close()
    return redirect(url_for("odemeler_sayfasi"))

@app.route("/odemeler")
def odemeler_sayfasi():
    db = get_db()

    odemeler = db.execute("""
        SELECT
            odemeler.*,
            uyeler.ad,
            uyeler.soyad
        FROM odemeler
        LEFT JOIN uyeler ON uyeler.id = odemeler.uye_id
        ORDER BY odemeler.id DESC
    """).fetchall()

    giderler = db.execute("""
        SELECT *
        FROM giderler
        ORDER BY id DESC
    """).fetchall()

    toplam_tutar = 0.0
    for odeme in odemeler:
        try:
            toplam_tutar += float(str(odeme["tutar"]).replace(",", "."))
        except (TypeError, ValueError):
            pass

    toplam_gider = 0.0
    for gider in giderler:
        try:
            toplam_gider += float(str(gider["tutar"]).replace(",", "."))
        except (TypeError, ValueError):
            pass

    db.close()

    return render_template(
        "dashboard.html",
        uyeler=[],
        toplam=0,
        aktif=0,
        yaklasan=0,
        dolan=0,
        bugun=0,
        bugun_bitenler=[],
        arama="",
        odemeler=odemeler,
        toplam_tutar=toplam_tutar,
        giderler=giderler,
        toplam_gider=toplam_gider,
        sayfa="odemeler"
    )

@app.route("/yoklama")
def yoklama_sayfasi():
    tarih = request.args.get("tarih", date.today().isoformat()).strip()

    try:
        datetime.strptime(tarih, "%Y-%m-%d")
    except ValueError:
        tarih = date.today().isoformat()

    db = get_db()

    uyeler = db.execute("""
        SELECT id, ad, soyad, telefon
        FROM uyeler
        ORDER BY ad COLLATE NOCASE, soyad COLLATE NOCASE
    """).fetchall()

    kayitlar = db.execute("""
        SELECT uye_id, geldi
        FROM yoklamalar
        WHERE tarih = ?
    """, (tarih,)).fetchall()

    durumlar = {kayit["uye_id"]: bool(kayit["geldi"]) for kayit in kayitlar}

    yoklama = [
        dict(uye, geldi=durumlar.get(uye["id"], False))
        for uye in uyeler
    ]

    db.close()

    return render_template(
        "dashboard.html",
        uyeler=[],
        toplam=0,
        aktif=0,
        yaklasan=0,
        dolan=0,
        bugun=0,
        bugun_bitenler=[],
        arama="",
        yoklama=yoklama,
        yoklama_tarihi=tarih,
        sayfa="yoklama"
    )


@app.route("/yoklama/kaydet", methods=["POST"])
def yoklama_kaydet():
    tarih = request.form.get("tarih", "").strip()

    try:
        datetime.strptime(tarih, "%Y-%m-%d")
    except ValueError:
        return redirect(url_for("yoklama_sayfasi"))

    gelenler = {
        int(uye_id)
        for uye_id in request.form.getlist("gelen_uye")
        if uye_id.isdigit()
    }

    db = get_db()

    uyeler = db.execute("SELECT id FROM uyeler").fetchall()

    for uye in uyeler:
        uye_id = uye["id"]
        geldi = 1 if uye_id in gelenler else 0

        db.execute("""
            INSERT INTO yoklamalar (uye_id, tarih, geldi)
            VALUES (?, ?, ?)
            ON CONFLICT(uye_id, tarih)
            DO UPDATE SET geldi = excluded.geldi
        """, (uye_id, tarih, geldi))

    db.commit()
    db.close()

    return redirect(url_for("yoklama_sayfasi", tarih=tarih))


@app.route("/api/uye/<int:uye_id>/odemeler")
def uye_odemeler(uye_id):
    db = get_db()

    odemeler = db.execute("""
        SELECT *
        FROM odemeler
        WHERE uye_id = ?
        ORDER BY id DESC
    """, (uye_id,)).fetchall()

    db.close()

    return jsonify([dict(o) for o in odemeler])



SMS_WORKER_TOKEN = os.environ.get("SMS_WORKER_TOKEN", "").strip()


def sms_worker_yetkili():
    if not SMS_WORKER_TOKEN:
        return False

    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {SMS_WORKER_TOKEN}"


def sms_mesaj_dogrula(mesaj):
    mesaj = str(mesaj or "").strip()

    if not mesaj:
        return None, "Mesaj boş olamaz."

    if len(mesaj) > 1000:
        return None, "Mesaj en fazla 1000 karakter olabilir."

    return mesaj, None


def sms_telefon_dogrula(telefon):
    telefon = str(telefon or "").strip()

    if not telefon:
        return None

    return telefon


def sms_job_ekle(db, uye_id, telefon, mesaj, simdi):
    db.execute("""
        INSERT INTO sms_jobs
        (uye_id, phone, message, status, attempts, created_at)
        VALUES (?, ?, ?, 'pending', 0, ?)
    """, (uye_id, telefon, mesaj, simdi))


@app.route("/api/sms/gonder", methods=["POST"])
def sms_gonder():
    data = request.get_json(silent=True) or {}

    try:
        uye_id = int(data.get("uye_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "mesaj": "Geçersiz üye."}), 400

    mesaj, hata = sms_mesaj_dogrula(data.get("mesaj"))
    if hata:
        return jsonify({"ok": False, "mesaj": hata}), 400

    db = get_db()

    uye = db.execute("""
        SELECT id, telefon
        FROM uyeler
        WHERE id = ?
    """, (uye_id,)).fetchone()

    if not uye:
        db.close()
        return jsonify({"ok": False, "mesaj": "Üye bulunamadı."}), 404

    telefon = sms_telefon_dogrula(uye["telefon"])

    if not telefon:
        db.close()
        return jsonify({
            "ok": False,
            "mesaj": "Üyenin telefon numarası kayıtlı değil."
        }), 400

    simdi = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    sms_job_ekle(db, uye_id, telefon, mesaj, simdi)

    db.commit()
    db.close()

    return jsonify({
        "ok": True,
        "kuyruga_alindi": 1,
        "mesaj": "SMS gönderim kuyruğuna alındı."
    })


@app.route("/api/sms/duyuru", methods=["POST"])
def sms_duyuru():
    data = request.get_json(silent=True) or {}
    uye_ids = data.get("uye_ids")

    if not isinstance(uye_ids, list) or not uye_ids:
        return jsonify({
            "ok": False,
            "mesaj": "En az bir üye seçmelisiniz."
        }), 400

    mesaj, hata = sms_mesaj_dogrula(data.get("mesaj"))
    if hata:
        return jsonify({"ok": False, "mesaj": hata}), 400

    temiz_ids = []

    for uye_id in uye_ids:
        try:
            uye_id = int(uye_id)
        except (TypeError, ValueError):
            continue

        if uye_id > 0 and uye_id not in temiz_ids:
            temiz_ids.append(uye_id)

    if not temiz_ids:
        return jsonify({
            "ok": False,
            "mesaj": "Geçerli üye seçimi bulunamadı."
        }), 400

    db = get_db()
    placeholders = ",".join("?" for _ in temiz_ids)

    uyeler = db.execute(f"""
        SELECT id, telefon
        FROM uyeler
        WHERE id IN ({placeholders})
    """, tuple(temiz_ids)).fetchall()

    simdi = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    kuyruga_alinan = 0
    telefonsuz = 0

    for uye in uyeler:
        telefon = sms_telefon_dogrula(uye["telefon"])

        if not telefon:
            telefonsuz += 1
            continue

        sms_job_ekle(db, uye["id"], telefon, mesaj, simdi)
        kuyruga_alinan += 1

    db.commit()
    db.close()

    return jsonify({
        "ok": True,
        "kuyruga_alindi": kuyruga_alinan,
        "telefonsuz": telefonsuz,
        "mesaj": f"{kuyruga_alinan} SMS gönderim kuyruğuna alındı."
    })


@app.route("/api/sms/worker/next", methods=["GET"])
def sms_worker_next():
    if not sms_worker_yetkili():
        return jsonify({
            "ok": False,
            "mesaj": "Yetkisiz worker."
        }), 401

    db = get_db()
    simdi = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    db.execute("""
        UPDATE sms_jobs
        SET status = 'pending',
            locked_at = NULL
        WHERE status = 'processing'
          AND locked_at < datetime('now', '-5 minutes')
    """)

    job = db.execute("""
        SELECT id, uye_id, phone, message, attempts
        FROM sms_jobs
        WHERE status = 'pending'
        ORDER BY id ASC
        LIMIT 1
    """).fetchone()

    if not job:
        db.commit()
        db.close()
        return jsonify({
            "ok": True,
            "job": None
        })

    db.execute("""
        UPDATE sms_jobs
        SET status = 'processing',
            attempts = attempts + 1,
            locked_at = ?
        WHERE id = ?
          AND status = 'pending'
    """, (simdi, job["id"]))

    db.commit()

    claimed = db.execute("""
        SELECT id, uye_id, phone, message, attempts
        FROM sms_jobs
        WHERE id = ?
          AND status = 'processing'
    """, (job["id"],)).fetchone()

    db.close()

    if not claimed:
        return jsonify({
            "ok": True,
            "job": None
        })

    return jsonify({
        "ok": True,
        "job": dict(claimed)
    })


@app.route("/api/sms/worker/result", methods=["POST"])
def sms_worker_result():
    if not sms_worker_yetkili():
        return jsonify({
            "ok": False,
            "mesaj": "Yetkisiz worker."
        }), 401

    data = request.get_json(silent=True) or {}

    try:
        job_id = int(data.get("job_id"))
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "mesaj": "Geçersiz job_id."
        }), 400

    status = str(data.get("status", "")).strip().lower()

    if status not in ("sent", "failed"):
        return jsonify({
            "ok": False,
            "mesaj": "Geçersiz sonuç durumu."
        }), 400

    hata = str(data.get("error") or "").strip()

    if len(hata) > 1000:
        hata = hata[:1000]

    db = get_db()

    if status == "sent":
        db.execute("""
            UPDATE sms_jobs
            SET status = 'sent',
                sent_at = ?,
                locked_at = NULL,
                error = NULL
            WHERE id = ?
        """, (
            datetime.utcnow().isoformat(timespec="seconds") + "Z",
            job_id
        ))
    else:
        db.execute("""
            UPDATE sms_jobs
            SET status = 'failed',
                locked_at = NULL,
                error = ?
            WHERE id = ?
        """, (hata or "SMS gönderilemedi.", job_id))

    db.commit()
    db.close()

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
