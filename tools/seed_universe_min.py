#!/usr/bin/env python3
"""
Minimal deterministic seed for DEV SQLite to unblock UI rendering.
Creates 3 groups → 3 subgroups each → 5 categories each → 50 assets.
Idempotent (safe to run multiple times).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal, engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


def seed_universe_min():
    """Seed minimal universe structure"""
    with engine.connect() as conn:
        # Ensure tables exist
        from database import init_database
        init_database()
        
        # Check if already seeded (idempotent check)
        result = conn.execute(text("SELECT COUNT(*) FROM groups"))
        group_count = result.scalar()
        
        if group_count >= 3:
            print(f"Universe already seeded ({group_count} groups found). Skipping.")
            return
        
        print("Seeding minimal universe structure...")
        
        # Clear existing data for clean seed
        conn.execute(text("DELETE FROM assets"))
        conn.execute(text("DELETE FROM categories"))
        conn.execute(text("DELETE FROM subgroups"))
        conn.execute(text("DELETE FROM groups"))
        conn.commit()
        
        # Seed 3 groups
        groups = []
        for i in range(3):
            gname = f"Group {i+1}"
            conn.execute(text("INSERT INTO groups (name) VALUES (:name)"), {"name": gname})
            gid = conn.execute(text("SELECT last_insert_rowid()")).scalar()
            groups.append((gid, gname))
        
        # Seed 3 subgroups per group
        subgroups = []
        for gid, gname in groups:
            for j in range(3):
                sgname = f"{gname} - Subgroup {j+1}"
                conn.execute(text("INSERT INTO subgroups (group_id, name) VALUES (:gid, :name)"), 
                           {"gid": gid, "name": sgname})
                sgid = conn.execute(text("SELECT last_insert_rowid()")).scalar()
                subgroups.append((sgid, sgname, gid))
        
        # Seed 5 categories per subgroup
        categories = []
        for sgid, sgname, gid in subgroups:
            for k in range(5):
                cname = f"{sgname} - Category {k+1}"
                conn.execute(text("INSERT INTO categories (subgroup_id, name) VALUES (:sgid, :name)"), 
                           {"sgid": sgid, "name": cname})
                cid = conn.execute(text("SELECT last_insert_rowid()")).scalar()
                categories.append((cid, cname, sgid))
        
        # Seed 50 assets distributed across categories
        asset_count = 0
        for cid, cname, sgid in categories:
            assets_per_cat = max(1, 50 // len(categories))
            for a in range(assets_per_cat):
                if asset_count >= 50:
                    break
                symbol = f"AST{asset_count+1:03d}"
                name = f"Asset {asset_count+1} - {cname}"
                conn.execute(text("""
                    INSERT INTO assets (symbol, name, category_id, is_active, exchange, country, currency)
                    VALUES (:symbol, :name, :cid, 1, 'NYSE', 'US', 'USD')
                """), {"symbol": symbol, "name": name, "cid": cid})
                asset_count += 1
            if asset_count >= 50:
                break
        
        conn.commit()
        print(f"Seeded: {len(groups)} groups, {len(subgroups)} subgroups, {len(categories)} categories, {asset_count} assets")


if __name__ == '__main__':
    seed_universe_min()
