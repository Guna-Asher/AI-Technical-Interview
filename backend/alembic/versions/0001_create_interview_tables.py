"""create interview tables

Revision ID: 0001
Revises: 
Create Date: 2026-10-19 18:00:53.448905
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('interview_sessions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=100), nullable=False),
    sa.Column('candidate_profile', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='created', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('created', 'in_progress', 'completed')", name=op.f('ck_interview_sessions_status')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_interview_sessions'))
    )
    op.create_table('interview_questions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('question_text', sa.Text(), nullable=False),
    sa.Column('topic', sa.String(length=100), nullable=True),
    sa.Column('difficulty', sa.String(length=20), nullable=True),
    sa.Column('source_chunks', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('position >= 1', name=op.f('ck_interview_questions_position')),
    sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], name=op.f('fk_interview_questions_session_id_interview_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_interview_questions')),
    sa.UniqueConstraint('session_id', 'position', name=op.f('uq_interview_questions_session_id'))
    )
    op.create_table('interview_reports',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('strengths', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('improvement_topics', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('recommendations', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], name=op.f('fk_interview_reports_session_id_interview_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_interview_reports')),
    sa.UniqueConstraint('session_id', name=op.f('uq_interview_reports_session_id'))
    )
    op.create_table('candidate_answers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('question_id', sa.Uuid(), nullable=False),
    sa.Column('answer_text', sa.Text(), nullable=False),
    sa.Column('feedback', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['interview_questions.id'], name=op.f('fk_candidate_answers_question_id_interview_questions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_candidate_answers')),
    sa.UniqueConstraint('question_id', name=op.f('uq_candidate_answers_question_id'))
    )


def downgrade() -> None:
    op.drop_table('candidate_answers')
    op.drop_table('interview_reports')
    op.drop_table('interview_questions')
    op.drop_table('interview_sessions')
