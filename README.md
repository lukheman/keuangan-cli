# keuangan-cli — mini tool-nya bot-keuangan-telegram

Versi CLI dari `bot-keuangan-telegram`. Database-nya sama persis, jadi saldo dan
transaksi selalu sinkron dengan bot Telegram dan dashboard web.

## Setup (sekali saja)

```bash
cd ~/Code/keuangan-cli
cp .env.example .env
# lalu isi .env (copy dari .env bot-keuangan-telegram, wajib SAMA persis):
#   DATABASE_URL, TELEGRAM_TOKEN, dst.
# lalu buat .cli.env:
#   KEUANGAN_TELEGRAM_ID=1117819481
#   KEUANGAN_BOT_PATH=/home/ubuntu/Code/bot-keuangan-telegram
uv sync
```

## Pakai

```bash
uv run keuangan.py saldo
uv run keuangan.py catat --tipe keluar --nominal 15000 --desc "Nasi ayam" --dompet BRI
uv run keuangan.py catat --tipe masuk --nominal 4500000 --desc "Gaji" --dompet BRI --kategori Kerja
uv run keuangan.py ringkasan --periode bulanan
uv run keuangan.py list --dompet BRI --limit 20
uv run keuangan.py            # mode interaktif (menu angka)
```

Nilai `--tipe`: `masuk`/`keluar` (alias: INCOME/EXPENSE).
Nilai `--periode`: `harian`/`mingguan`/`bulanan`.
