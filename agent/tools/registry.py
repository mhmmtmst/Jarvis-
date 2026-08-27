from dataclasses import dataclass
from functools import partial
from typing import Callable

from agent.memory import delete_memory, recall, remember
from agent.tools.browser import open_browser, play_media
from agent.tools.files import search_files
from agent.tools.open_app import open_app
from agent.tools.report import get_projects_report
from agent.tools.screen import read_screen
from agent.tools.system_info import get_system_info
from agent.tools.terminal import run_command
from agent.tools.weather import get_weather_summary


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., dict]


def build_tool_registry(
    client,
    weather_default_location: str = "",
    report_projects: list[tuple[str, str]] | None = None,
    search_default_root: str = "",
) -> dict[str, ToolSpec]:
    return {
        "open_app": ToolSpec(
            name="open_app",
            description="Kullanıcının bilgisayarında bir uygulama veya dosya açar.",
            parameters={
                "type": "object",
                "properties": {
                    "isim": {
                        "type": "string",
                        "description": "Açılacak uygulamanın veya dosyanın adı",
                    }
                },
                "required": ["isim"],
            },
            handler=open_app,
        ),
        "get_system_info": ToolSpec(
            name="get_system_info",
            description="Bilgisayarın CPU, RAM, disk ve batarya kullanım yüzdelerini döner.",
            parameters={"type": "object", "properties": {}},
            handler=get_system_info,
        ),
        "open_browser": ToolSpec(
            name="open_browser",
            description="Tarayıcıda bir arama yapar veya doğrudan bir URL açar. Kullanıcı bir şey aramak isterse veya bir siteyi/URL'i açmak isterse bu tool'u kullan.",
            parameters={
                "type": "object",
                "properties": {
                    "query_or_url": {
                        "type": "string",
                        "description": "Aranacak kelime/cümle veya açılacak URL",
                    }
                },
                "required": ["query_or_url"],
            },
            handler=open_browser,
        ),
        "run_command": ToolSpec(
            name="run_command",
            description=(
                "Kullanıcının bilgisayarında bir PowerShell komutu çalıştırır ve çıktısını döner. "
                "Bilinen tehlikeli komut kalıpları (format, shutdown, disk silme vb.) tamamen engellenir. "
                "Dosya silme veya süreç/servis durdurma gibi riskli ama tamamen yasak olmayan komutlarda "
                "sonuç status='needs_confirmation' döner — bu durumda kullanıcıdan sözlü onay al, "
                "onaylarsa AYNI komutu confirmed=true ile tekrar çağır."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Çalıştırılacak PowerShell komutu",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Komutun çalışacağı klasör (opsiyonel, verilmezse mevcut klasör kullanılır)",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "Kullanıcı riskli komutu onayladıysa true geç (varsayılan false)",
                    },
                },
                "required": ["command"],
            },
            handler=run_command,
        ),
        "play_media": ToolSpec(
            name="play_media",
            description="YouTube veya Spotify'da bir şarkı/video arar ve arama sonuç sayfasını tarayıcıda açar (otomatik çalmaz, kullanıcı ilk sonuca tıklamalı).",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Aranacak şarkı/video/sanatçı",
                    },
                    "platform": {
                        "type": "string",
                        "description": "youtube veya spotify",
                        "enum": ["youtube", "spotify"],
                    },
                },
                "required": ["query"],
            },
            handler=play_media,
        ),
        "read_screen": ToolSpec(
            name="read_screen",
            description="Kullanıcının ekranının bir görüntüsünü alır ve Gemini'ye tarif ettirir. Kullanıcı ekranda ne olduğunu sorarsa veya ekrandaki bir şeyi analiz etmeni isterse kullan.",
            parameters={
                "type": "object",
                "properties": {
                    "soru": {
                        "type": "string",
                        "description": "Ekran hakkında sorulacak soru (opsiyonel)",
                    }
                },
                "required": [],
            },
            handler=partial(read_screen, client=client),
        ),
        "remember": ToolSpec(
            name="remember",
            description=(
                "Kullanıcı hakkında kalıcı bir bilgiyi kategori/anahtar/değer olarak kaydeder. "
                "Kullanıcı 'bunu hatırla' derse veya kişisel bir bilgi paylaşırsa (isim, tercih, proje bilgisi vb.) kullan. "
                "Aynı category+key tekrar kaydedilirse üzerine yazılır, yinelenen kayıt oluşmaz. "
                "category için identity (kimlik bilgisi), preferences (tercihler) veya notes (genel not) kullan; emin değilsen notes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Bilgi kategorisi: identity, preferences veya notes",
                    },
                    "key": {
                        "type": "string",
                        "description": "Bilginin kısa anahtarı, örn. 'isim', 'kedi_adi', 'sevdigi_renk'",
                    },
                    "value": {
                        "type": "string",
                        "description": "Hatırlanacak değer",
                    },
                },
                "required": ["key", "value"],
            },
            handler=remember,
        ),
        "recall": ToolSpec(
            name="recall",
            description="Daha önce hatırlanan tüm bilgileri döner. Kullanıcı 'ne hatırlıyorsun' derse veya geçmişte söylediği bir şeye referans verirse kullan.",
            parameters={"type": "object", "properties": {}},
            handler=recall,
        ),
        "delete_memory": ToolSpec(
            name="delete_memory",
            description=(
                "Hatırlanan bir bilgiyi siler. category+key biliniyorsa ikisini birden ver (kesin silme); "
                "bilinmiyorsa match_text ile içerikte arama yaparak siler. Kullanıcı 'şunu unut' / 'onu sil' derse kullan."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Silinecek kaydın kategorisi (key ile birlikte, kesin silme için)",
                    },
                    "key": {
                        "type": "string",
                        "description": "Silinecek kaydın anahtarı (category ile birlikte, kesin silme için)",
                    },
                    "match_text": {
                        "type": "string",
                        "description": "Kategori/anahtar bilinmiyorsa, kayıtlarda aranacak metin",
                    },
                },
                "required": [],
            },
            handler=delete_memory,
        ),
        "get_weather": ToolSpec(
            name="get_weather",
            description="Güncel hava durumunu döner. Konum verilmezse kullanıcının IP adresinden bulunduğu şehir otomatik tespit edilir.",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Hava durumu sorulacak şehir (opsiyonel, verilmezse otomatik tespit edilir)",
                    }
                },
                "required": [],
            },
            handler=partial(get_weather_summary, default_location=weather_default_location),
        ),
        "get_projects_report": ToolSpec(
            name="get_projects_report",
            description=(
                "Bilinen proje klasörlerinin (Odakla, ChronoPlay, doğum günü sitesi, Jarvis) "
                "git durumunu döner: branch, commit'lenmemiş değişiklik sayısı, son commit. "
                "Kullanıcı 'rapor ver', 'projelerde durum ne', 'neyi yarım bıraktım' derse "
                "kullan. Cevaplarken önemli olanı öne çıkar: temiz/güncel projelerden tek "
                "cümleyle bahset, commit'lenmemiş değişikliği olan projeleri detaylandır. "
                "Not: last_commit içindeki relative_date değeri git tarafından her zaman "
                "İngilizce döner (örn. '5 minutes ago'); kullanıcıya seslendirirken bunu "
                "Türkçeye çevir (örn. '5 dakika önce')."
            ),
            parameters={"type": "object", "properties": {}, "required": []},
            handler=partial(get_projects_report, projects=report_projects or []),
        ),
        "search_files": ToolSpec(
            name="search_files",
            description=(
                "Bir klasör ağacında dosya adında veya metin içeriğinde bir kelime/ifadeyi arar. "
                "Kullanıcı 'X ile ilgili dosyayı bul', 'geçen hafta yazdığım Y nerede' gibi bir şey "
                "sorarsa kullan. root verilmezse kullanıcının yapılandırılmış varsayılan arama "
                "klasöründe (veya o da yoksa home dizininde) arar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Aranacak kelime/ifade (dosya adında veya içeriğinde)",
                    },
                    "root": {
                        "type": "string",
                        "description": "Aramanın yapılacağı klasör (opsiyonel)",
                    },
                },
                "required": ["query"],
            },
            handler=partial(search_files, default_root=search_default_root),
        ),
    }
