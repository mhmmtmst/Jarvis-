# Jarvis — "Rapor Ver" Proje Durumu Özeti Tasarımı

## Amaç

Jarvis projesinin orijinal ilham kaynağı olan demo fikri: kullanıcı "Jarvis,
rapor ver" dediğinde, bilinen proje klasörlerinin git durumunu (branch,
commit'lenmemiş değişiklik, son commit) tarayıp sesli bir özet vermesi.
`run_command` tool'u zaten var ama bu, güvenilir/yapılandırılmış bir çıktı
için ayrı, amaca özel bir tool olarak yapılıyor (serbest komut çalıştırıp
çıktıyı ayrıştırmak yerine).

Kapsam: **sadece git durumu okuma**. Build/test çalıştırma, deploy tetikleme
gibi şeyler bu tasarımın dışında (bkz. backlog idea 2 — Odakla release tool,
ayrı bir tasarım).

## Yapısal bulgu — paylaşılan repo

Bilinen proje klasörlerinden **Odakla, doğum günü sitesi ve jarvis'in
kendisi aynı git deposunun** (`C:/Users/mhmmt`, home dizini) farklı alt
klasörleri — ayrı repo değiller. Sadece **ChronoPlay** kendi ayrı reposuna
sahip. Hiçbirinin (ChronoPlay dahil) remote'u yok.

Sonuç:
- "Push edilmemiş commit / ahead-behind" kavramı hiçbir projeye uygulanmıyor,
  tasarımda yer almıyor.
- Paylaşılan repo (Odakla/doğum-günü/jarvis) için **branch bilgisi bir kere**
  söylenir (hepsi aynı anda aynı branch'te), sonra her proje için sadece
  **o path altındaki commit'lenmemiş dosya sayısı** ve **son commit**
  ayrı ayrı raporlanır.
- ChronoPlay ayrı repo olduğu için kendi branch'i ayrıca belirtilir.

## Mimari

`agent/tools/report.py` + registry'ye yeni bir `get_projects_report` tool'u.
Diğer tool'larla aynı pattern: tool **yapılandırılmış veri** döner, sesli
cümleye çevirmeyi persona/Gemini yapar (`get_weather` ile birebir aynı ayrım).

```python
def get_projects_report(config: ReportConfig, runner=None) -> dict:
    # runner=None ise subprocess.run kullanılır (agent/tools/terminal.py'deki
    # run_command ile aynı enjeksiyon deseni, testte sahte runner verilir)
    """
    Döner: {
      "repos": [
        {
          "toplevel": "C:/Users/mhmmt",
          "branch": "master",
          "projects": [
            {"name": "Odakla", "changed_files": 0, "last_commit": {...} | None},
            {"name": "Jarvis", "changed_files": 3, "last_commit": {...}},
            ...
          ]
        },
        {
          "toplevel": "C:/Users/mhmmt/OneDrive/Masaüstü/chronoplay",
          "branch": "main",
          "projects": [{"name": "ChronoPlay", "changed_files": 12, "last_commit": {...}}]
        }
      ]
    }
    """
```

Adımlar (her yapılandırılmış proje için):
1. `git -C <path> rev-parse --show-toplevel` → hangi repoya ait olduğunu
   bul, aynı toplevel'e sahip projeleri grupla.
2. Grup başına bir kere `git -C <toplevel> branch --show-current`.
3. Proje başına `git -C <toplevel> status --porcelain -- <path>` → satır
   sayısı = değişen dosya sayısı.
4. Proje başına `git -C <toplevel> log -1 --format=%s|%ar -- <path>` → son
   commit mesajı + göreli tarih (path altında hiç commit yoksa `None`).

Hata durumu: bir path git deposu değilse veya path yoksa (`rev-parse` hata
verirse), o proje `{"name": ..., "error": "..."}" olarak işaretlenir, diğer
projeler etkilenmez (tek bir bozuk yapılandırma tüm raporu düşürmemeli).

## Konfigürasyon

`.env`'e yeni değişken:

```
JARVIS_REPORT_PROJECTS=Odakla:C:/Users/mhmmt/OneDrive/Masaüstü/Odakla,ChronoPlay:C:/Users/mhmmt/OneDrive/Masaüstü/chronoplay,DogumGunuSitesi:C:/Users/mhmmt/OneDrive/Masaüstü/projeler/doğum günü,Jarvis:C:/Users/mhmmt/OneDrive/Masaüstü/jarvis
```

`agent/config.py`'de `İsim:yol` çiftlerine ayrıştırılıp `ReportConfig`'e
(basit bir `list[tuple[str, str]]` veya `dataclass`) dönüştürülür. Boş/tanımsızsa
tool "hiç proje yapılandırılmamış" hatası döner (Gemini bunu kullanıcıya
söyler).

**Parsing notu:** Windows path'leri sürücü harfinden sonra kendi `:`'sini
içerdiği için (`C:/Users/...`), her çift `split(":", 1)` ile (sadece **ilk**
`:` üzerinden, isim/yol ayracı) ayrıştırılmalı — `split(":")` (sınırsız)
kullanılırsa path'in kendi `:`'si de bölünüp yolu bozar.

## Tool tanımı ve persona rehberi

Registry'deki `ToolSpec` açıklaması Gemini'ye şunu net anlatmalı: bu tool
"önemli olanı öne çıkar" mantığıyla kullanılmalı — temiz/güncel projelerden
tek cümleyle bahsedilsin, commit'lenmemiş değişikliği olan projeler
detaylandırılsın. Bu, tool'un dönen veriye değil, `persona.py`'deki mevcut
"[SISTEM]" ve few-shot örnek konvansiyonuna yeni bir örnek eklenerek
sağlanır (örn. "Asistan, rapor ver" → `get_projects_report` çağrısı → özet
konuşma tarzı örneği).

## Çıktı yüzeyi

Sadece sesli + mevcut CONVERSATION panelinde metin olarak görünür. WEATHER
gibi kalıcı bir HUD kartı **yok** — bu on-demand bir sorgu, periyodik
güncellenen bir durum değil.

## Test planı

`agent/tests/test_report.py`:
- Path gruplama: iki path aynı toplevel'e sahipse tek repo girdisi altında
  toplanmalı.
- `subprocess.run` mock'lanarak: tümü temiz senaryosu, bazıları kirli
  senaryosu, git-olmayan bir path senaryosu (hata izolasyonu).
- Boş `JARVIS_REPORT_PROJECTS` senaryosu.
- `agent/tests/test_registry.py`'ye yeni tool'un registry'ye doğru
  bağlandığını doğrulayan bir vaka eklenir (mevcut desen).

## Kapsam dışı (bilinçli)

- Build/test/deploy tetikleme (idea 2, ayrı tasarım).
- Ahead/behind remote karşılaştırması (hiçbir repoda remote yok).
- Ayrı bir HUD kartı.
- Gün sonu proaktif tetikleme (idea 21, "gün sonu özeti" — bu tool'u
  kullanabilir ama tetikleme mantığı kendi tasarımında ele alınacak).
