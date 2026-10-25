#!/usr/bin/env python3
"""keuangan-cli: versi CLI dari bot-keuangan-telegram, database yang sama.

Contoh:
    python keuangan.py saldo
    python keuangan.py catat --tipe keluar --nominal 15000 --desc "Nasi ayam" --dompet BRI
    python keuangan.py catat --tipe masuk --nominal 4500000 --desc "Gaji TJS" --dompet BRI --kategori Kerja
    python keuangan.py ringkasan --periode bulanan
    python keuangan.py list --dompet BRI --limit 20
    python keuangan.py            (mode interaktif)
"""

import argparse
import asyncio
import decimal
import os
import sys

# --- muat .env milik CLI ---
try:
    from dotenv import load_dotenv
    _here = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_here, ".env"))
    load_dotenv(os.path.join(_here, ".cli.env"))
except ImportError:
    pass

# CLI tidak pernah memanggil Telegram API, tapi validasi config bot mewajibkan
# TELEGRAM_TOKEN ada. Isi dummy bila user menghapusnya dari .env.
os.environ.setdefault("TELEGRAM_TOKEN", "cli-dummy-token")

BOT_PATH = os.getenv("KEUANGAN_BOT_PATH", "/home/ubuntu/Code/bot-keuangan-telegram")
TELEGRAM_ID = int(os.getenv("KEUANGAN_TELEGRAM_ID", "0") or 0)
if BOT_PATH not in sys.path:
    sys.path.insert(0, BOT_PATH)

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models import User, Wallet, Transaction  # noqa: E402
from app.models.category import TransactionType  # noqa: E402
from app.services.transaction_service import record_transaction  # noqa: E402
from app.services import report_service  # noqa: E402
from sqlalchemy import select, desc  # noqa: E402
from sqlalchemy.orm import joinedload  # noqa: E402
from app.core.timezone import to_local_datetime  # noqa: E402


class _TU:
    """User Telegram palsu: service bot hanya butuh id/username/full_name."""

    def __init__(self, telegram_id: int):
        self.id = telegram_id
        self.username = f"cli-{telegram_id}"
        self.full_name = f"CLI {telegram_id}"


def _norm_tipe(raw: str) -> TransactionType:
    r = (raw or "").strip().upper()
    if r in ("INCOME", "MASUK", "PEMASUKAN", "IN", "M"):
        return TransactionType.INCOME
    if r in ("EXPENSE", "KELUAR", "PENGELUARAN", "OUT", "BELANJA", "K"):
        return TransactionType.EXPENSE
    raise ValueError("tipe harus masuk/INCOME atau keluar/EXPENSE")


def _rp(n) -> str:
    return f"Rp{float(n):,.0f}".replace(",", ".")


async def cmd_saldo() -> int:
    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.telegram_id == TELEGRAM_ID))).scalar_one_or_none()
        if not user:
            print("User belum ada. Catat satu transaksi dulu via bot/CLI.");
            return 1
        wallets = (await s.execute(select(Wallet).where(Wallet.user_id == user.id))).scalars().all()
        total = sum(float(w.balance) for w in wallets)
        print("--- Saldo ---")
        for w in wallets:
            mark = " (utama)" if w.is_primary else ""
            print(f"{w.name}{mark}: {_rp(w.balance)}")
        print(f"TOTAL: {_rp(total)}")
    return 0


async def cmd_catat(tipe: str, nominal: str, desc_: str, dompet: str | None, kategori: str | None) -> int:
    amount = decimal.Decimal(str(nominal))
    if amount <= 0:
        print("Nominal harus lebih dari 0.");
        return 1
    if not (desc_ or "").strip():
        print("Deskripsi wajib diisi.");
        return 1
    tx = await record_transaction(_TU(TELEGRAM_ID), amount, desc_.strip(), _norm_tipe(tipe), kategori, dompet)
    print(f"Tercatat: {tx.type.value} {_rp(tx.amount)} - {tx.description} "
          f"({getattr(tx, 'category_name', '-')} / {getattr(tx, 'wallet_name', '-')})")
    return 0


async def cmd_ringkasan(periode: str) -> int:
    p = (periode or "harian").strip().lower()
    today = await report_service.get_user_local_date(TELEGRAM_ID)
    if p in ("harian", "hari", "today"):
        txs, masuk, keluar = await report_service.get_daily_summary(TELEGRAM_ID, today)
        label = f"harian {today.isoformat()}"
    elif p in ("mingguan", "minggu"):
        txs, masuk, keluar = await report_service.get_weekly_summary(TELEGRAM_ID, today)
        label = f"mingguan s/d {today.isoformat()}"
    else:
        txs, masuk, keluar = await report_service.get_monthly_summary(TELEGRAM_ID, today.year, today.month)
        label = f"bulanan {today.year}-{today.month:02d}"
    if txs is None:
        print("User tidak ditemukan.");
        return 1
    print(f"--- Ringkasan {label} ---")
    print(f"Masuk : {_rp(masuk)} ({sum(1 for t in txs if str(t.type).endswith('INCOME'))}x)")
    print(f"Keluar: {_rp(keluar)} ({sum(1 for t in txs if str(t.type).endswith('EXPENSE'))}x)")
    print(f"Selisih: {_rp(masuk - keluar)}")
    return 0


async def cmd_list(dompet: str, limit: int) -> int:
    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.telegram_id == TELEGRAM_ID))).scalar_one_or_none()
        if not user:
            print("User tidak ditemukan.");
            return 1
        rows = (await s.execute(
            select(Transaction).options(joinedload(Transaction.category), joinedload(Transaction.wallet))
            .where(Transaction.user_id == user.id).order_by(desc(Transaction.created_at))
        )).scalars().all()
        shown = 0
        for t in rows:
            wname = t.wallet.name if t.wallet else "-"
            if dompet and dompet.strip().lower() not in wname.lower():
                continue
            cname = t.category.name if t.category else "-"
            try:
                dstr = to_local_datetime(t.created_at, user.timezone).date().isoformat()
            except Exception:
                dstr = "-"
            print(f"{dstr} | {t.type.value:7} | {_rp(t.amount):>15} | {cname} | {t.description} [{wname}]")
            shown += 1
            if shown >= limit:
                break
        if shown == 0:
            print("Tidak ada transaksi.")
    return 0


def _tanya(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    ans = input(f"{prompt}{suffix}: ").strip()
    return ans or default


async def cmd_interaktif() -> int:
    print("=== Keuangan CLI (ketik angka) ===")
    print("1. Catat pengeluaran\n2. Catat pemasukan\n3. Cek saldo\n4. Ringkasan\n5. List transaksi\n0. Keluar")
    pilih = _tanya("Pilih", "3")
    if pilih == "1":
        return await cmd_catat("keluar", _tanya("Nominal"), _tanya("Deskripsi"),
                               _tanya("Dompet (kosongkan=default)") or None,
                               _tanya("Kategori (kosongkan=otomatis)") or None)
    if pilih == "2":
        return await cmd_catat("masuk", _tanya("Nominal"), _tanya("Deskripsi"),
                               _tanya("Dompet (kosongkan=default)") or None,
                               _tanya("Kategori (kosongkan=otomatis)") or None)
    if pilih == "3":
        return await cmd_saldo()
    if pilih == "4":
        return await cmd_ringkasan(_tanya("Periode (harian/mingguan/bulanan)", "harian"))
    if pilih == "5":
        return await cmd_list(_tanya("Filter dompet (kosongkan=semua)"), int(_tanya("Limit", "20") or 20))
    print("Sampai jumpa.")
    return 0


def main() -> int:
    if not TELEGRAM_ID:
        print("KEUANGAN_TELEGRAM_ID belum diset di .cli.env.");
        return 1
    ap = argparse.ArgumentParser(description="keuangan-cli")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("saldo", help="cek saldo dompet")
    p = sub.add_parser("catat", help="catat transaksi")
    p.add_argument("--tipe", required=True, help="masuk/keluar")
    p.add_argument("--nominal", required=True)
    p.add_argument("--desc", required=True)
    p.add_argument("--dompet", default=None)
    p.add_argument("--kategori", default=None)
    p = sub.add_parser("ringkasan", help="ringkasan harian/mingguan/bulanan")
    p.add_argument("--periode", default="harian")
    p = sub.add_parser("list", help="list transaksi")
    p.add_argument("--dompet", default="")
    p.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    if args.cmd == "saldo":
        return asyncio.run(cmd_saldo())
    if args.cmd == "catat":
        return asyncio.run(cmd_catat(args.tipe, args.nominal, args.desc, args.dompet, args.kategori))
    if args.cmd == "ringkasan":
        return asyncio.run(cmd_ringkasan(args.periode))
    if args.cmd == "list":
        return asyncio.run(cmd_list(args.dompet, args.limit))
    return asyncio.run(cmd_interaktif())


if __name__ == "__main__":
    raise SystemExit(main())
