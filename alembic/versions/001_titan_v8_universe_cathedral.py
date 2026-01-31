"""Titan V8 Universe Cathedral

Revision ID: 001_titan_v8
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_titan_v8'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgcrypto extension for gen_random_uuid()
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')
    
    # Create universe_assets table
    op.create_table(
        'universe_assets',
        sa.Column('asset_id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('symbol', sa.String(32), nullable=False, unique=True, index=True),
        sa.Column('morton_code', sa.BigInteger(), nullable=False),
        sa.Column('taxonomy32', sa.Integer(), nullable=False, comment='[3b Domain | 1b Outlier | 16b Risk Score | 12b Reserved]'),
        sa.Column('meta32', sa.Integer(), nullable=False, comment='[8b Risk | 8b Shock | 2b Trend | 6b Vitality | 8b Reserved]'),
        sa.Column('x', sa.Float(), nullable=False),
        sa.Column('y', sa.Float(), nullable=False),
        sa.Column('z', sa.Float(), nullable=False),
        sa.Column('fidelity_score', sa.Float(), nullable=False),
        sa.Column('spin', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('governance_status', sa.String(32), nullable=False, server_default='PROVISIONAL'),
        sa.Column('vertex_buffer', postgresql.BYTEA(), nullable=False),
        sa.Column('last_quantum_update', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('cluster_id', sa.Integer(), nullable=True),
        sa.Column('adjacency_bitset', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.CheckConstraint('fidelity_score >= 0 AND fidelity_score <= 1', name='ck_universe_fidelity_0_1'),
        sa.CheckConstraint('octet_length(vertex_buffer) = 28', name='ck_universe_vertex_stride_28'),
    )
    
    # Create indices
    op.create_index('idx_universe_morton', 'universe_assets', ['morton_code'], unique=False)
    op.create_index('idx_universe_cluster', 'universe_assets', ['cluster_id'], unique=False)
    op.create_index('idx_universe_fidelity_high', 'universe_assets', ['fidelity_score'], unique=False, postgresql_where=sa.text('fidelity_score > 0.7'))
    
    # Create materialized view: sovereign_universe
    # Extract domain from taxonomy32: (taxonomy32 >> 29) & 7
    op.execute("""
        CREATE MATERIALIZED VIEW sovereign_universe AS
        SELECT
            asset_id,
            morton_code,
            taxonomy32,
            meta32,
            x, y, z,
            fidelity_score,
            governance_status,
            vertex_buffer,
            last_quantum_update,
            cluster_id,
            adjacency_bitset,
            (taxonomy32 >> 29) & 7 AS sector_id
        FROM universe_assets
        WHERE governance_status IN ('PROVISIONAL', 'SANCTIONED')
          AND fidelity_score > 0.85
        ORDER BY morton_code;
    """)
    
    # Create index on materialized view
    op.create_index('idx_sovereign_morton', 'sovereign_universe', ['morton_code'], unique=False)


def downgrade() -> None:
    # Drop materialized view index
    op.drop_index('idx_sovereign_morton', table_name='sovereign_universe')
    
    # Drop materialized view
    op.execute('DROP MATERIALIZED VIEW IF EXISTS sovereign_universe')
    
    # Drop indices on universe_assets
    op.drop_index('idx_universe_fidelity_high', table_name='universe_assets')
    op.drop_index('idx_universe_cluster', table_name='universe_assets')
    op.drop_index('idx_universe_morton', table_name='universe_assets')
    
    # Drop table
    op.drop_table('universe_assets')
