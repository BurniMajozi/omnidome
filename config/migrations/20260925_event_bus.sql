-- Event bus (SPEC-event-bus.md): transactional outbox, subscriptions, per-consumer
-- deliveries, notifications feed. Idempotent. Also applied at consumer startup by
-- services/common/event_bus.ensure_schema() (keep the two identical).
CREATE TABLE IF NOT EXISTS domain_events (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    source VARCHAR(60) NOT NULL,
    subject_type VARCHAR(60),
    subject_id VARCHAR(100),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_domain_events_idempotency
    ON domain_events (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_domain_events_subject
    ON domain_events (tenant_id, subject_type, subject_id, created_at);
CREATE INDEX IF NOT EXISTS ix_domain_events_type
    ON domain_events (tenant_id, event_type, created_at);

CREATE TABLE IF NOT EXISTS event_subscriptions (
    consumer VARCHAR(60) NOT NULL,
    event_pattern VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, event_pattern)
);

CREATE TABLE IF NOT EXISTS event_deliveries (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES domain_events(id) ON DELETE CASCADE,
    consumer VARCHAR(60) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_until TIMESTAMPTZ,
    last_error TEXT,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_event_deliveries_event_consumer UNIQUE (event_id, consumer)
);
CREATE INDEX IF NOT EXISTS ix_event_deliveries_due
    ON event_deliveries (consumer, next_attempt_at) WHERE status IN ('pending', 'processing');
CREATE INDEX IF NOT EXISTS ix_event_deliveries_status ON event_deliveries (status, created_at);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    recipient_id UUID,
    category VARCHAR(40) NOT NULL DEFAULT 'general',
    severity VARCHAR(10) NOT NULL DEFAULT 'info',
    title VARCHAR(200) NOT NULL,
    body TEXT,
    link VARCHAR(300),
    source VARCHAR(60),
    subject_type VARCHAR(60),
    subject_id VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_notifications_feed ON notifications (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_notifications_unread ON notifications (tenant_id) WHERE read_at IS NULL;
