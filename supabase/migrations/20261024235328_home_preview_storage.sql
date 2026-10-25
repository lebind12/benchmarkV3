-- Dedicated home preview storage. Existing fixture baseline must already exist.


CREATE TABLE home_preview_snapshot (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	fixture_id BIGINT NOT NULL,
	fingerprint VARCHAR(64) NOT NULL,
	payload JSONB NOT NULL,
	as_of TIMESTAMP WITH TIME ZONE NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT home_preview_snapshot_input_uq UNIQUE (fixture_id, fingerprint),
	FOREIGN KEY(fixture_id) REFERENCES fixture (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_home_preview_snapshot_fixture_id ON home_preview_snapshot (fixture_id);

ALTER TABLE home_preview_snapshot ENABLE ROW LEVEL SECURITY;


CREATE TABLE home_preview_version (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	fixture_id BIGINT NOT NULL,
	snapshot_id BIGINT NOT NULL,
	fingerprint VARCHAR(64) NOT NULL,
	payload JSONB NOT NULL,
	generated_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT home_preview_version_input_uq UNIQUE (fixture_id, fingerprint),
	FOREIGN KEY(fixture_id) REFERENCES fixture (id) ON DELETE CASCADE,
	FOREIGN KEY(snapshot_id) REFERENCES home_preview_snapshot (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_home_preview_version_fixture_id ON home_preview_version (fixture_id);

ALTER TABLE home_preview_version ENABLE ROW LEVEL SECURITY;


CREATE TABLE home_preview_publication (
	fixture_id BIGINT NOT NULL,
	version_id BIGINT,
	identity VARCHAR(64) NOT NULL,
	refresh_state TEXT DEFAULT 'idle' NOT NULL,
	last_attempt_at TIMESTAMP WITH TIME ZONE,
	reason TEXT,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (fixture_id),
	CONSTRAINT home_preview_refresh_state_ck CHECK (refresh_state IN ('idle','queued','running','failed')),
	FOREIGN KEY(fixture_id) REFERENCES fixture (id) ON DELETE CASCADE,
	FOREIGN KEY(version_id) REFERENCES home_preview_version (id) ON DELETE SET NULL
)

;

ALTER TABLE home_preview_publication ENABLE ROW LEVEL SECURITY;


CREATE TABLE home_preview_attempt (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	fixture_id BIGINT NOT NULL,
	slot TIMESTAMP WITH TIME ZONE NOT NULL,
	state TEXT NOT NULL,
	owner VARCHAR(36) NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	finished_at TIMESTAMP WITH TIME ZONE,
	usage JSONB DEFAULT '{}' NOT NULL,
	reason TEXT,
	PRIMARY KEY (id),
	CONSTRAINT home_preview_attempt_slot_uq UNIQUE (fixture_id, slot),
	CONSTRAINT home_preview_attempt_state_ck CHECK (state IN ('running','succeeded','failed','interrupted','unchanged','deferred')),
	FOREIGN KEY(fixture_id) REFERENCES fixture (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_home_preview_attempt_fixture_id ON home_preview_attempt (fixture_id);

ALTER TABLE home_preview_attempt ENABLE ROW LEVEL SECURITY;
