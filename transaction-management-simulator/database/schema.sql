-- ============================================================================
-- Transaction Management and Concurrency Control Simulator
-- Database Schema for Supabase PostgreSQL
-- ============================================================================
-- SAFETY NOTE:
-- This script creates ONLY simulator-specific tables prefixed with 'sim_'.
-- It NEVER drops existing schemas or user data. It is safe and idempotent.
-- ============================================================================

-- Table 1: Dedicated simulator test data (simulated isolated resource)
CREATE TABLE IF NOT EXISTS sim_test_data (
    item_id VARCHAR(50) PRIMARY KEY,
    item_name VARCHAR(100) NOT NULL,
    value NUMERIC(14, 2) NOT NULL DEFAULT 100.00,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table 2: Execution runs history and experiment outcomes
CREATE TABLE IF NOT EXISTS sim_runs (
    run_id VARCHAR(36) PRIMARY KEY,
    scenario_name VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    status VARCHAR(50) NOT NULL,
    initial_value NUMERIC(14, 2),
    final_value NUMERIC(14, 2),
    expected_value NUMERIC(14, 2),
    details JSONB DEFAULT '{}'::jsonb
);

-- Table 3: Fine-grained transaction events and operation history
CREATE TABLE IF NOT EXISTS sim_events (
    event_id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES sim_runs(run_id) ON DELETE CASCADE,
    transaction_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observed_value NUMERIC(14, 2),
    step_number INT DEFAULT 0
);

-- Indexes for performance and quick query retrieval
CREATE INDEX IF NOT EXISTS idx_sim_events_run_id ON sim_events(run_id);
CREATE INDEX IF NOT EXISTS idx_sim_events_timestamp ON sim_events(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_sim_runs_started_at ON sim_runs(started_at DESC);

-- Safe seed initialization for test item
INSERT INTO sim_test_data (item_id, item_name, value, updated_at)
VALUES ('SIM_DATA_ITEM_ALPHA', 'Engineering Test Resource X', 100.00, CURRENT_TIMESTAMP)
ON CONFLICT (item_id) DO UPDATE
SET item_name = EXCLUDED.item_name;

-- Table 4: Dedicated consistency test table with explicit CHECK constraint
CREATE TABLE IF NOT EXISTS sim_consistency_data (
    item_id VARCHAR(50) PRIMARY KEY,
    item_name VARCHAR(100) NOT NULL,
    value NUMERIC(14, 2) NOT NULL CHECK (value >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Safe seed initialization for consistency resource
INSERT INTO sim_consistency_data (item_id, item_name, value, updated_at)
VALUES ('SIM_CONSISTENCY_X', 'Constrained Test Resource (CHECK value >= 0)', 100.00, CURRENT_TIMESTAMP)
ON CONFLICT (item_id) DO UPDATE
SET item_name = EXCLUDED.item_name;

