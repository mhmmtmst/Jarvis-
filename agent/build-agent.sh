#!/usr/bin/env bash
#
# agent.exe build script — "how do I rebuild the frozen Python agent?"
#
# Bu dosya, agent.exe'nin nasil uretildiginin TEK dogru kaynagidir (single
# source of truth). Task 7'nin electron-builder `extraResources` ayari buradan
# cikan `agent-dist/agent/` klasorunu paketler.
#
# Kullanim (Git Bash, repo kokunden ya da baska bir yerden — fark etmez):
#
#     ./agent/build-agent.sh
#
# Cikti: agent-dist/agent/agent.exe (+ agent-dist/agent/_internal/) ~130 MB
#
# Dogrulama (calistigini gormek icin):
#
#     JARVIS_ENV_PATH="$(pwd)/agent/.env" ./agent-dist/agent/agent.exe
#
#   Beklenen: "Jarvis agent baslatiliyor..." log satiri + 8765 portu LISTENING
#   (netstat -ano | findstr 8765). Ctrl+C ile durdurulur.

set -euo pipefail

# Betik nerede olursa olsun repo kokunden calis: PyInstaller'a verilen
# `--paths .` ve tum goreli yollar repo koku varsayimina dayaniyor.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="./agent/venv/Scripts/python.exe"

if [ ! -x "$PYTHON" ]; then
  echo "HATA: $PYTHON bulunamadi. Once venv'i kurun:" >&2
  echo "  python -m venv agent/venv" >&2
  echo "  ./agent/venv/Scripts/python.exe -m pip install -r agent/requirements.txt" >&2
  exit 1
fi

# --- On kosullar --------------------------------------------------------------
# PyInstaller bir build araci; kasitli olarak requirements.txt'de DEGIL.
# Pillow ise gercek bir runtime bagimliligi (agent/tools/screen.py ekran
# analizi icin kullaniyor) ve requirements.txt'de listeli, ama venv'de eksik
# kalabiliyor — eksikse agent.exe icine hic girmez. Ikisi de idempotent.
echo "==> On kosullar kuruluyor (pyinstaller + Pillow)..."
"$PYTHON" -m pip install --quiet pyinstaller Pillow

# --- Build --------------------------------------------------------------------
# --collect-all speech_recognition:
#   SpeechRecognition'in veri dosyalari (ozellikle recognize_google'in ses
#   donusumu icin kullandigi flac-win32.exe) otomatik toplanmazsa donmus exe
#   calisma aninda patlar.
#
# --exclude-module torch/whisper/numba/llvmlite/tiktoken:
#   ZORUNLU — bunlar olmadan build 650 MB oluyor (130 MB yerine).
#   Sebep: --collect-all speech_recognition, paketin TUM alt modullerini
#   topluyor; bunlarin arasindaki
#   `speech_recognition/recognizers/whisper_local/whisper.py` dosyasinda
#   TYPE_CHECKING ile korunmayan, fonksiyon govdesi icinde `import torch`
#   (satir 59) ve `import whisper` (satir 94) var. PyInstaller fonksiyon ici
#   importlari da takip ettigi icin torch (366 MB) + numba/llvmlite (115 MB)
#   bundle'a giriyor.
#   Jarvis bu kod yoluna HIC girmiyor: agent/wake_word.py yalnizca
#   `recognize_google` cagiriyor (saf HTTP), recognize_whisper/vosk/sphinx
#   hicbir yerde kullanilmiyor. Yani bu 520 MB tamamen olu agirlik.
#   NOT: torch/whisper paylasilan venv'de baska bir isten (video duzenleme)
#   arta kalmis durumda; venv temizlense bile bu bayraklar zararsiz.
#
# --exclude-module pytest:
#   Test bagimliligi, uretim bundle'inda isi yok.
#
# --exclude-module openwakeword/onnxruntime/scikit-learn/scipy:
#   ZORUNLU (torch/whisper ile AYNI bug sinifi) — agent/wake_word.py'deki
#   OpenWakeWordDetector su an aktif kullanilmayan olu kod, ama __init__
#   icinde fonksiyon govdesinde `from openwakeword.model import Model` var.
#   openwakeword requirements.txt'de listeli oldugu icin (venv'e gercekten
#   kuruluysa) PyInstaller bu fonksiyon-ici importu da statik olarak takip
#   edip openwakeword + onnxruntime (36MB) + scikit-learn (13MB) + scipy
#   (47MB+20MB libs) bundle'a sokuyor — toplam ~120MB tamamen olu agirlik.
#   Jarvis bu kod yoluna HIC girmiyor: wake_word.py'de gercekte kullanilan
#   tek dedektor _WAKE_PATTERN tabanli metin eslesmesi (recognize_google
#   ciktisinda "asistan" kelimesini arar), OpenWakeWordDetector hic
#   instantiate edilmiyor.
echo "==> PyInstaller build calisiyor..."
./agent/venv/Scripts/pyinstaller.exe \
  --name agent \
  --onedir \
  --distpath agent-dist \
  --workpath build/pyinstaller \
  --specpath build \
  --paths . \
  --collect-all speech_recognition \
  --exclude-module torch \
  --exclude-module whisper \
  --exclude-module numba \
  --exclude-module llvmlite \
  --exclude-module tiktoken \
  --exclude-module openwakeword \
  --exclude-module onnxruntime \
  --exclude-module sklearn \
  --exclude-module scipy \
  --exclude-module pytest \
  --noconfirm \
  agent_entry.py

# --- Sonuc --------------------------------------------------------------------
if [ ! -f "agent-dist/agent/agent.exe" ]; then
  echo "HATA: build bitti ama agent-dist/agent/agent.exe olusmamis." >&2
  exit 1
fi

echo ""
echo "==> Build tamam: agent-dist/agent/agent.exe"
du -sh agent-dist/agent 2>/dev/null || true
echo "    (beklenen boyut ~130 MB; 600 MB+ goruyorsaniz --exclude-module"
echo "     bayraklarindan biri dusmus demektir)"
