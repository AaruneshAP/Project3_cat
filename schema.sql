-- schema.sql
-- Tickets table for NLP Maintenance Log Classification (Project 3)
-- Stores raw text, model predictions, confidence scores, and metadata.

CREATE TABLE IF NOT EXISTS tickets (
    id                 SERIAL PRIMARY KEY,
    text               TEXT          NOT NULL,
    predicted_category VARCHAR(100),
    confidence         FLOAT,
    true_category      VARCHAR(100),
    equipment_id       VARCHAR(100),
    created_at         TIMESTAMP     DEFAULT NOW()
);
