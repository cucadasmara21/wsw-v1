#!/usr/bin/env python3
"""
Titan V8 Quantum Reality Verification Script
Validates database state and API endpoint correctness.
"""
import sys
import struct
import requests
from pathlib import Path

# Add project root to path
root_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_path))

try:
    import asyncpg
except ImportError:
    print("ERROR: asyncpg required. Install: pip install asyncpg")
    sys.exit(1)

try:
    from config import settings
except ImportError as e:
    print(f"ERROR: Failed to import config: {e}")
    sys.exit(1)

VERTEX_STRIDE = 28
VERTEX_FORMAT = "<IIfffff"
VERTEX_UNPACKER = struct.Struct(VERTEX_FORMAT)


async def verify_database(dsn: str) -> bool:
    """Verify database state"""
    print("\n=== Database Verification ===")
    
    try:
        conn = await asyncpg.connect(dsn)
        
        # Check row count
        count = await conn.fetchval("SELECT COUNT(*) FROM universe_assets")
        print(f"✓ Row count: {count}")
        
        if count < 10000:
            print(f"⚠ WARNING: Row count {count} < 10000")
            return False
        
        # Check vertex_buffer lengths
        invalid_lengths = await conn.fetchval("""
            SELECT COUNT(*) FROM universe_assets
            WHERE octet_length(vertex_buffer) != 28
        """)
        print(f"✓ Invalid vertex_buffer lengths: {invalid_lengths}")
        
        if invalid_lengths > 0:
            print(f"✗ ERROR: {invalid_lengths} rows have invalid vertex_buffer length")
            return False
        
        # Random sample unpack test
        sample = await conn.fetch("""
            SELECT vertex_buffer, taxonomy32, meta32, x, y, z, fidelity_score
            FROM universe_assets
            ORDER BY RANDOM()
            LIMIT 25
        """)
        
        print(f"✓ Testing random sample (N={len(sample)})")
        for row in sample:
            buf = bytes(row['vertex_buffer'])
            if len(buf) != 28:
                print(f"✗ ERROR: Sample vertex_buffer length {len(buf)} != 28")
                return False
            
            try:
                tax, meta, x, y, z, fid, spin = VERTEX_UNPACKER.unpack(buf)
                # Validate ranges
                if not (0.0 <= fid <= 1.0):
                    print(f"✗ ERROR: Sample fidelity {fid} not in [0,1]")
                    return False
                
                # Cross-check with DB values
                if abs(tax - (row['taxonomy32'] & 0xFFFFFFFF)) > 0:
                    print(f"⚠ WARNING: Taxonomy mismatch in sample")
                if abs(meta - (row['meta32'] & 0xFFFFFFFF)) > 0:
                    print(f"⚠ WARNING: Meta mismatch in sample")
            except struct.error as e:
                print(f"✗ ERROR: Failed to unpack sample: {e}")
                return False
        
        # Check fidelity range
        invalid_fidelity = await conn.fetchval("""
            SELECT COUNT(*) FROM universe_assets
            WHERE fidelity_score < 0 OR fidelity_score > 1
        """)
        print(f"✓ Invalid fidelity scores: {invalid_fidelity}")
        
        if invalid_fidelity > 0:
            print(f"✗ ERROR: {invalid_fidelity} rows have invalid fidelity_score")
            return False
        
        # Check morton_code range (63 bits)
        invalid_morton = await conn.fetchval("""
            SELECT COUNT(*) FROM universe_assets
            WHERE morton_code < 0 OR morton_code >= 9223372036854775808
        """)
        print(f"✓ Invalid morton_code values: {invalid_morton}")
        
        if invalid_morton > 0:
            print(f"✗ ERROR: {invalid_morton} rows have invalid morton_code (must fit 63 bits)")
            return False
        
        await conn.close()
        print("✓ Database verification PASSED")
        return True
        
    except Exception as e:
        print(f"✗ ERROR: Database verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_api_endpoint(base_url: str = "http://localhost:8000") -> bool:
    """Verify API endpoint"""
    print("\n=== API Endpoint Verification ===")
    
    try:
        url = f"{base_url}/api/universe/v8/snapshot?format=vertex28&compression=zstd"
        
        # Head request first
        resp = requests.head(url, timeout=10)
        print(f"✓ HEAD request: {resp.status_code}")
        
        if resp.status_code == 204:
            print("⚠ WARNING: Endpoint returned 204 (no content)")
            return False
        
        if resp.status_code != 200:
            print(f"✗ ERROR: Endpoint returned {resp.status_code}")
            return False
        
        # Check headers
        stride = resp.headers.get("X-Vertex-Stride")
        asset_count = resp.headers.get("X-Asset-Count")
        version = resp.headers.get("X-Titan-Version")
        
        print(f"✓ X-Titan-Version: {version}")
        print(f"✓ X-Vertex-Stride: {stride}")
        print(f"✓ X-Asset-Count: {asset_count}")
        
        if stride != "28":
            print(f"✗ ERROR: X-Vertex-Stride != 28 (got {stride})")
            return False
        
        asset_count_int = int(asset_count) if asset_count else 0
        if asset_count_int < 10000:
            print(f"⚠ WARNING: X-Asset-Count {asset_count_int} < 10000")
        
        # GET request with decompression
        resp = requests.get(url, timeout=30)
        print(f"✓ GET request: {resp.status_code}, Content-Length: {len(resp.content)}")
        
        if resp.status_code != 200:
            print(f"✗ ERROR: GET returned {resp.status_code}")
            return False
        
        # Decompress if zstd
        if resp.headers.get("Content-Encoding") == "zstd":
            try:
                import zstandard as zstd
                dctx = zstd.ZstdDecompressor()
                payload = dctx.decompress(resp.content)
                print(f"✓ Decompressed: {len(payload)} bytes")
            except ImportError:
                print("⚠ WARNING: zstandard not available, skipping decompression test")
                payload = resp.content
        else:
            payload = resp.content
        
        # Validate payload
        if len(payload) == 0:
            print("✗ ERROR: Empty payload")
            return False
        
        if len(payload) % 28 != 0:
            print(f"✗ ERROR: Payload length {len(payload)} not multiple of 28")
            return False
        
        # Unpack first vertex
        try:
            first_vertex = payload[0:28]
            tax, meta, x, y, z, fid, spin = VERTEX_UNPACKER.unpack(first_vertex)
            print(f"✓ First vertex unpacked: tax={tax}, meta={meta}, x={x:.3f}, y={y:.3f}, z={z:.3f}, fid={fid:.3f}, spin={spin:.3f}")
            
            if not (0.0 <= fid <= 1.0):
                print(f"✗ ERROR: First vertex fidelity {fid} not in [0,1]")
                return False
        except struct.error as e:
            print(f"✗ ERROR: Failed to unpack first vertex: {e}")
            return False
        
        print("✓ API endpoint verification PASSED")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"✗ ERROR: API request failed: {e}")
        return False
    except Exception as e:
        print(f"✗ ERROR: API verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main verification function"""
    dsn = settings.DATABASE_URL
    if not dsn or dsn.startswith("sqlite"):
        print("ERROR: DATABASE_URL must be a PostgreSQL connection string")
        sys.exit(1)
    
    print("Titan V8 Quantum Reality Verification")
    print("=" * 50)
    
    db_ok = await verify_database(dsn)
    api_ok = verify_api_endpoint()
    
    print("\n" + "=" * 50)
    if db_ok and api_ok:
        print("✓ ALL VERIFICATIONS PASSED")
        sys.exit(0)
    else:
        print("✗ VERIFICATION FAILED")
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
