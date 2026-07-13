# Nakit Akış — Cash Flow Management

Türkçe nakit akış yönetim uygulaması. Çekler, senetler, giderler, banka hesapları ve yaklaşan ödemeleri tek ekrandan yönetin.

## Özellikler

- 🏦 **Banka Hesapları** — Bakiye takibi
- 📄 **Çekler** — Alınan / Verilen çekler, vade & durum yönetimi
- 📜 **Senetler** — Alacak / Borç senetleri
- 💸 **Giderler & Gelirler** — 12 kategori, tarih bazlı takip
- 📊 **Dashboard** — KPI kartları, 6 aylık gelir/gider grafiği, kategori dağılımı
- 🔔 **Otomatik Hatırlatmalar** — Vadeden 3 ve 1 gün önce email + uygulama içi bildirim (her sabah 09:00 TR)
- 📥 **CSV Export** — Tüm listeler Excel uyumlu dışa aktarım
- 🔐 **Google OAuth** — Emergent yönetimli, güvenli oturum

## Teknoloji

- **Frontend**: React 19, Tailwind CSS, Shadcn/UI, Recharts, React Router 7
- **Backend**: FastAPI (Python 3.11+), Motor (MongoDB async)
- **Veritabanı**: MongoDB
- **Email**: [Resend](https://resend.com)
- **Zamanlama**: APScheduler
- **Kimlik doğrulama**: Emergent Google OAuth

## Kurulum

### Gereksinimler
- Python 3.11+
- Node.js 18+
- Yarn
- MongoDB (yerel veya bulut)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env       # Değerleri düzenleyin
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### Frontend

```bash
cd frontend
yarn install
cp .env.example .env       # REACT_APP_BACKEND_URL ayarlayın
yarn start
```

## Ortam Değişkenleri

### backend/.env
| Değişken | Açıklama |
|---|---|
| `MONGO_URL` | MongoDB bağlantı stringi |
| `DB_NAME` | Veritabanı adı |
| `RESEND_API_KEY` | Resend API key ([resend.com](https://resend.com)) |
| `SENDER_EMAIL` | Doğrulanmış gönderici, örn `Nakit Akış <bildirim@domain.com>` |
| `CORS_ORIGINS` | Virgülle ayrılmış izinli origin listesi |

### frontend/.env
| Değişken | Açıklama |
|---|---|
| `REACT_APP_BACKEND_URL` | Backend public URL |

## API Endpoint'leri

Tümü `/api` ön ekli ve session cookie / Bearer token gerektirir.

| Method | Endpoint | Açıklama |
|---|---|---|
| POST | `/api/auth/session` | OAuth session_id → session_token |
| GET | `/api/auth/me` | Mevcut kullanıcı |
| POST | `/api/auth/logout` | Oturumu kapat |
| CRUD | `/api/bank-accounts` | Banka hesapları |
| CRUD | `/api/checks` | Çekler |
| CRUD | `/api/promissory-notes` | Senetler |
| CRUD | `/api/expenses` | Giderler |
| CRUD | `/api/incomes` | Gelirler |
| GET | `/api/dashboard/summary` | Dashboard verisi |
| GET | `/api/notifications` | Bildirim listesi |
| POST | `/api/notifications/check-reminders` | Manuel hatırlatma tetikle |
| GET | `/api/export/{checks,promissory-notes,expenses,incomes}` | CSV export |

## Otomatik Hatırlatmalar

Her gün **06:00 UTC (09:00 Türkiye)** APScheduler tüm kullanıcıların bekleyen çek/senetlerini tarar. Vadesi **3 gün** ve **1 gün** sonra olan ödemeler için:
1. Uygulama içi bildirim (badge + dropdown)
2. Email (Resend, HTML formatlı)

Kullanıcı **"Kontrol Et"** butonu ile anlık tetikleyebilir.

## Lisans

Bu proje kişisel kullanım içindir. Ticari kullanım için sahibiyle iletişime geçin.

---

*Emergent ile inşa edildi.*
