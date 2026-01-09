#!/usr/bin/env python3
"""Seed demo risk snapshot data.
Usage: python seed_demo_data.py --reset --days 60
Creates groups, subgroups, categories, assets and fills risk_snapshots table with generated data.
"""
import argparse
import random
from datetime import datetime, timedelta
from typing import List

from database import SessionLocal, engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import time


def reset_db(conn):
    conn.execute(text("DELETE FROM risk_snapshots"))


def seed_structure(conn, n_groups=2, subgroups_per_group=5, categories_per_subgroup=2, assets_per_category=3):
    grp_names = ["Traditional", "Alternative"]
    group_ids = []
    # wipe existing structure for idempotency
    conn.execute(text("DELETE FROM assets"))
    conn.execute(text("DELETE FROM categories"))
    conn.execute(text("DELETE FROM subgroups"))
    conn.execute(text("DELETE FROM groups"))

    for gi in range(n_groups):
        gname = grp_names[gi] if gi < len(grp_names) else f"Group {gi+1}"
        conn.execute(text("INSERT INTO groups (name) VALUES (:name)"), {"name": gname})
        gid = conn.execute(text("SELECT last_insert_rowid()" )).scalar_one()
        group_ids.append((gid, gname))

    subgroup_ids = []
    for gid, gname in group_ids:
        for si in range(subgroups_per_group):
            sname = f"{gname}-Subgroup-{si+1}"
            conn.execute(text("INSERT INTO subgroups (group_id, name) VALUES (:gid, :name)"), {"gid": gid, "name": sname})
            sid = conn.execute(text("SELECT last_insert_rowid()" )).scalar_one()
            subgroup_ids.append((sid, sname, gid))

    category_ids = []
    for sid, sname, gid in subgroup_ids:
        for ci in range(categories_per_subgroup):
            cname = f"{sname}-Cat-{ci+1}"
            conn.execute(text("INSERT INTO categories (subgroup_id, name) VALUES (:sid, :name)"), {"sid": sid, "name": cname})
            cid = conn.execute(text("SELECT last_insert_rowid()" )).scalar_one()
            category_ids.append((cid, cname, sid))

    asset_ids = []
    # Build map from subgroup id to group name
    gid_to_name = {g[0]:g[1] for g in group_ids}
    for cid, cname, sid in category_ids:
        for ai in range(assets_per_category):
            sym = f"AS{cid}_{ai+1}"
            aname = f"{cname}-Asset-{ai+1}"
            group_name = gid_to_name.get(next((g for g in group_ids if g[0]==next((s[2] for s in subgroup_ids if s[0]==sid), None)), (None,''))[0], '')
            subgroup_name = next((s[1] for s in subgroup_ids if s[0]==sid), '')
            conn.execute(text("INSERT INTO assets (symbol, name, category, group_name, sector, exchange, country, currency, is_active) VALUES (:sym, :name, :category, :group_name, :sector, :exchange, :country, :currency, 1)"), {"sym": sym, "name": aname, "category": cname, "group_name": group_name, "sector": '', "exchange": '', "country": '', "currency": 'USD'})
            aid = conn.execute(text("SELECT last_insert_rowid()" )).scalar_one()
            asset_ids.append((aid, aname, cid, sid))

    return group_ids, subgroup_ids, category_ids, asset_ids


def generate_snapshots(asset_rows: List[tuple], days=60, conn=None):
    # asset_rows: list of tuples (aid, aname, cid, sid)
    snapshots = []
    now = datetime.utcnow()

    # build mapping for category/subgroup/group names
    cat_map = {}
    sub_map = {}
    grp_map = {}
    if conn is not None:
        rows = conn.execute(text("SELECT id, name, subgroup_id FROM categories")).mappings().all()
        for r in rows:
            cat_map[r['id']] = r['name']
        rows = conn.execute(text("SELECT id, name, group_id FROM subgroups")).mappings().all()
        for r in rows:
            sub_map[r['id']] = {'name': r['name'], 'group_id': r['group_id']}
        rows = conn.execute(text("SELECT id, name FROM groups")).mappings().all()
        for r in rows:
            grp_map[r['id']] = r['name']

    for aid, aname, cid, sid in asset_rows:
        # base random starting vector
        price = random.uniform(30, 70)
        fund = random.uniform(20, 80)
        liq = random.uniform(10, 90)
        cp = random.uniform(0, 50)
        reg = random.uniform(0, 40)
        for d in range(days):
            ts = now - timedelta(days=days - d - 1)
            # small random drift
            price += random.uniform(-1.5, 1.5)
            fund += random.uniform(-1.0, 1.0)
            liq += random.uniform(-1.2, 1.2)
            cp += random.uniform(-0.8, 0.8)
            reg += random.uniform(-0.5, 0.5)

            # clamp 0-100
            price = max(0, min(100, price))
            fund = max(0, min(100, fund))
            liq = max(0, min(100, liq))
            cp = max(0, min(100, cp))
            reg = max(0, min(100, reg))

            cri = 0.30 * price + 0.25 * fund + 0.20 * liq + 0.15 * cp + 0.10 * reg

            group_name = grp_map.get(sub_map.get(sid, {}).get('group_id'), 'Unknown') if sid in sub_map else 'Unknown'
            subgroup_name = sub_map.get(sid, {}).get('name', 'Unknown')
            category_name = cat_map.get(cid, 'Unknown')

            snapshots.append({
                'ts': ts.isoformat(),
                'asset_id': str(aid),
                'asset_name': aname,
                'group_name': group_name,
                'subgroup_name': subgroup_name,
                'category_name': category_name,
                'price_risk': float(price),
                'fundamental_risk': float(fund),
                'liquidity_risk': float(liq),
                'counterparty_risk': float(cp),
                'regime_risk': float(reg),
                'cri': float(cri)
            })
    return snapshots


def batch_insert_snapshots(engine_or_conn, snapshots):
    BATCH = 250

    # Detect existing columns so we insert against the correct schema
    with engine_or_conn.connect() as chk:
        cols = chk.execute(text("PRAGMA table_info(risk_snapshots)")).mappings().all()
        existing_cols = {c['name'] for c in cols}

    base_cols = ['ts', 'asset_id', 'asset_name', 'group_name', 'subgroup_name', 'category_name', 'cri']

    # Map possible risk column name variants to snapshot keys
    col_map = {
        'price_risk': 'price_risk',
        'fundamental_risk': 'fundamental_risk',
        'fund_risk': 'fundamental_risk',
        'liquidity_risk': 'liquidity_risk',
        'liq_risk': 'liquidity_risk',
        'counterparty_risk': 'counterparty_risk',
        'cp_risk': 'counterparty_risk',
        'regime_risk': 'regime_risk',
        'regime': 'regime_risk',
        'model_version': 'model_version'
    }

    # Build the columns we'll insert into based on what's present in the table
    insert_cols = list(base_cols)
    for col_name in ['price_risk', 'fundamental_risk', 'fund_risk', 'liquidity_risk', 'liq_risk', 'counterparty_risk', 'cp_risk', 'regime_risk', 'regime', 'model_version']:
        if col_name in existing_cols:
            insert_cols.append(col_name)

    col_placeholders = ', '.join(insert_cols)
    param_placeholders = ', '.join([f":{c}" for c in insert_cols])
    insert_sql = text(f"INSERT INTO risk_snapshots ({col_placeholders}) VALUES ({param_placeholders})")

    for i in range(0, len(snapshots), BATCH):
        chunk = snapshots[i:i+BATCH]
        params = []
        for s in chunk:
            p = {}
            for c in insert_cols:
                if c in base_cols:
                    p[c] = s[c] if c in s else (s.get('cri') if c == 'cri' else None)
                else:
                    # map column aliases to snapshot keys
                    mapped = col_map.get(c, c)
                    # provide sensible defaults for new/required columns
                    if mapped == 'model_version' and mapped not in s:
                        p[c] = 'v1'
                    else:
                        p[c] = s.get(mapped)
            params.append(p)

        # Use a fresh transaction per batch and retry on SQLITE 'database is locked'
        retries = 5
        backoff = 0.2
        for attempt in range(retries):
            try:
                with engine_or_conn.begin() as trans_conn:
                    trans_conn.execute(insert_sql, params)
                print(f"Inserted batch {i // BATCH + 1} ({len(chunk)} rows)")
                break
            except OperationalError as e:
                if 'database is locked' in str(e).lower() and attempt < retries - 1:
                    wait = backoff * (2 ** attempt)
                    print(f"Database is locked, retrying batch {i // BATCH + 1} in {wait:.2f}s (attempt {attempt+1}/{retries})")
                    time.sleep(wait)
                    continue
                raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset', action='store_true')
    parser.add_argument('--days', type=int, default=60)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        with engine.connect() as conn:
            # Ensure risk_snapshots schema has expected columns
            cols = conn.execute(text("PRAGMA table_info(risk_snapshots) ")).mappings().all()
            existing = {c['name'] for c in cols}
            if 'asset_name' not in existing:
                print("Adding missing columns to risk_snapshots table...")
                conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN asset_name TEXT"))
            if 'group_name' not in existing:
                conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN group_name TEXT"))
            if 'subgroup_name' not in existing:
                conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN subgroup_name TEXT"))
            if 'category_name' not in existing:
                conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN category_name TEXT"))
            if 'fundamental_risk' not in existing:
                conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN fundamental_risk REAL"))
            if 'liquidity_risk' not in existing:
                conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN liquidity_risk REAL"))
            if 'counterparty_risk' not in existing:
                conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN counterparty_risk REAL"))
            cols = conn.execute(text("PRAGMA table_info(risk_snapshots) ")).mappings().all()
            existing = {c['name'] for c in cols}

        if args.reset:
            print("Resetting risk_snapshots table...")
            reset_db(db)
            db.commit()

        print("Seeding groups, subgroups, categories and assets... this may take a moment")
        groups, subgroups, categories, assets = seed_structure(db)
        # Commit structure changes so the Session does not hold DB locks during snapshot insertions
        db.commit()

        print(f"Generated {len(assets)} assets; generating snapshots ({args.days} days each)")
        with engine.connect() as conn:
            snapshots = generate_snapshots(assets, days=args.days, conn=conn)
            print(f"Inserting {len(snapshots)} snapshots")
            # Use the Engine to get fresh per-batch transactions to avoid nested transaction errors
            batch_insert_snapshots(engine, snapshots)

        print("Seeding complete")
    finally:
        db.close()


if __name__ == '__main__':
    main()
