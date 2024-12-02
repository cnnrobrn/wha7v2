"""Add instagram username column

Revision ID: add_instagram_username
Revises: previous_revision_hash
Create Date: 2024-12-01
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Add instagram_username column
    op.add_column('phone_numbers',
        sa.Column('instagram_username', sa.String(20), nullable=True)
    )
    # Add unique constraint
    op.create_unique_constraint(
        'uq_phone_numbers_instagram_username',
        'phone_numbers',
        ['instagram_username']
    )

def downgrade():
    # Remove the unique constraint first
    op.drop_constraint(
        'uq_phone_numbers_instagram_username',
        'phone_numbers',
        type_='unique'
    )
    # Then remove the column
    op.drop_column('phone_numbers', 'instagram_username')