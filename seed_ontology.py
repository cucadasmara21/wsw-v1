#!/usr/bin/env python3
"""
Seed ontology: Groups, Subgroups, Categories and demo Assets
Idempotent: can run multiple times without duplicates
"""
from database import SessionLocal, init_database
from models import Group, Subgroup, Category, Asset


def seed_ontology():
    """Create minimal ontology structure with demo assets"""
    db = SessionLocal()
    
    try:
        # Check if already seeded
        existing_groups = db.query(Group).count()
        if existing_groups > 0:
            print(f"✓ Ontology already seeded ({existing_groups} groups found)")
            return
        
        # Group 1: Equities
        g1 = Group(name="Equities")
        db.add(g1)
        db.flush()
        
        # Subgroups for Equities
        sg1_1 = Subgroup(name="US Tech", group_id=g1.id)
        sg1_2 = Subgroup(name="International", group_id=g1.id)
        db.add_all([sg1_1, sg1_2])
        db.flush()
        
        # Categories for US Tech
        cat1_1_1 = Category(name="Large Cap Tech", subgroup_id=sg1_1.id)
        cat1_1_2 = Category(name="Software & Cloud", subgroup_id=sg1_1.id)
        # Categories for International
        cat1_2_1 = Category(name="European Tech", subgroup_id=sg1_2.id)
        cat1_2_2 = Category(name="Emerging Markets", subgroup_id=sg1_2.id)
        db.add_all([cat1_1_1, cat1_1_2, cat1_2_1, cat1_2_2])
        db.flush()
        
        # Group 2: Fixed Income
        g2 = Group(name="Fixed Income")
        db.add(g2)
        db.flush()
        
        # Subgroups for Fixed Income
        sg2_1 = Subgroup(name="Government Bonds", group_id=g2.id)
        sg2_2 = Subgroup(name="Corporate Bonds", group_id=g2.id)
        db.add_all([sg2_1, sg2_2])
        db.flush()
        
        # Categories for Government Bonds
        cat2_1_1 = Category(name="US Treasuries", subgroup_id=sg2_1.id)
        cat2_1_2 = Category(name="International Sovereign", subgroup_id=sg2_1.id)
        # Categories for Corporate Bonds
        cat2_2_1 = Category(name="Investment Grade", subgroup_id=sg2_2.id)
        cat2_2_2 = Category(name="High Yield", subgroup_id=sg2_2.id)
        db.add_all([cat2_1_1, cat2_1_2, cat2_2_1, cat2_2_2])
        db.flush()
        
        # Demo Assets (10 per category in Large Cap Tech and Software & Cloud)
        tech_assets = [
            ("AAPL", "Apple Inc.", "Technology"),
            ("MSFT", "Microsoft Corporation", "Technology"),
            ("GOOGL", "Alphabet Inc.", "Technology"),
            ("AMZN", "Amazon.com Inc.", "Technology"),
            ("NVDA", "NVIDIA Corporation", "Technology"),
            ("META", "Meta Platforms Inc.", "Technology"),
            ("TSLA", "Tesla Inc.", "Technology"),
            ("BRK.B", "Berkshire Hathaway", "Financial Services"),
            ("V", "Visa Inc.", "Financial Services"),
            ("JPM", "JPMorgan Chase", "Financial Services"),
        ]
        
        for symbol, name, sector in tech_assets:
            asset = Asset(
                symbol=symbol,
                name=name,
                sector=sector,
                category_id=cat1_1_1.id,
                exchange="NASDAQ",
                country="US",
                currency="USD",
                is_active=True
            )
            db.add(asset)
        
        # Software & Cloud assets
        saas_assets = [
            ("CRM", "Salesforce Inc.", "Technology"),
            ("ADBE", "Adobe Inc.", "Technology"),
            ("NOW", "ServiceNow Inc.", "Technology"),
            ("ORCL", "Oracle Corporation", "Technology"),
            ("SAP", "SAP SE", "Technology"),
            ("INTU", "Intuit Inc.", "Technology"),
            ("SNOW", "Snowflake Inc.", "Technology"),
            ("TEAM", "Atlassian Corporation", "Technology"),
            ("ZM", "Zoom Video Communications", "Technology"),
            ("DDOG", "Datadog Inc.", "Technology"),
        ]
        
        for symbol, name, sector in saas_assets:
            asset = Asset(
                symbol=symbol,
                name=name,
                sector=sector,
                category_id=cat1_1_2.id,
                exchange="NASDAQ",
                country="US",
                currency="USD",
                is_active=True
            )
            db.add(asset)
        
        db.commit()
        
        # Summary
        groups_count = db.query(Group).count()
        subgroups_count = db.query(Subgroup).count()
        categories_count = db.query(Category).count()
        assets_count = db.query(Asset).count()
        
        print(f"✓ Ontology seeded successfully:")
        print(f"  - Groups: {groups_count}")
        print(f"  - Subgroups: {subgroups_count}")
        print(f"  - Categories: {categories_count}")
        print(f"  - Demo Assets: {assets_count}")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding ontology: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Initializing database...")
    init_database()
    print("\nSeeding ontology...")
    seed_ontology()
    print("\n✓ Done!")
