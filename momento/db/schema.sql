CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'gender') THEN
        CREATE TYPE gender AS ENUM ('male', 'female', 'other');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reservation_status') THEN
        CREATE TYPE reservation_status AS ENUM ('confirmed', 'cancelled', 'completed', 'no_show');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_status') THEN
        CREATE TYPE order_status AS ENUM (
            'created',
            'confirmed',
            'preparing',
            'ready',
            'picked_up',
            'on_the_way',
            'delivered',
            'cancelled'
        );
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'fulfillment_type') THEN
        CREATE TYPE fulfillment_type AS ENUM (
            'pickup',
            'delivery'
        );
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'payment_type') THEN
        CREATE TYPE payment_type AS ENUM (
            'credit_card',
            'debit_card',
            'paypal',
            'apple_pay',
            'google_pay',
            'cash'
        );
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'delivery_provider') THEN
        CREATE TYPE delivery_provider AS ENUM (
            'swiftdrop',
            'foodfly',
            'quickdish',
            'mealdash',
            'carryeats'
        );
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'membership_tier') THEN
        CREATE TYPE membership_tier AS ENUM (
            'basic',
            'silver',
            'gold',
            'platinum'
        );
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'membership_status') THEN
        CREATE TYPE membership_status AS ENUM (
            'active',
            'cancelled',
            'expired'
        );
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    gender gender,
    address1 TEXT,
    address2 TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    zip TEXT,
    phone TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payment_methods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    type payment_type NOT NULL,
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS restaurants (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    address TEXT,
    city TEXT,
    country TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    cuisines TEXT[],
    price_range_lower INTEGER,
    price_range_upper INTEGER,
    opening_hours JSONB,
    capacity INTEGER DEFAULT 40,
    amenities TEXT[] DEFAULT '{}',
    image_url TEXT[] DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS menu_items (
    id UUID PRIMARY KEY,
    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    categories TEXT[],
    cuisines TEXT[] DEFAULT '{}',
    price NUMERIC,
    image_url TEXT[] DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    time TIME NOT NULL,
    party_size INTEGER NOT NULL,
    special_requests TEXT,
    duration_minutes INTEGER NOT NULL DEFAULT 90,
    status reservation_status NOT NULL DEFAULT 'confirmed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,

    fulfillment fulfillment_type NOT NULL,
    status order_status NOT NULL DEFAULT 'created',

    total_price NUMERIC NOT NULL,
    currency TEXT DEFAULT 'USD',

    delivery_provider_name delivery_provider,
    delivery_address TEXT,

    special_instructions TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    menu_item_id UUID REFERENCES menu_items(id),
    name TEXT NOT NULL,
    price NUMERIC NOT NULL,
    quantity INTEGER NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_email
    ON users(email);

CREATE INDEX IF NOT EXISTS idx_menu_items_restaurant
    ON menu_items(restaurant_id);

CREATE INDEX IF NOT EXISTS idx_menu_items_name
    ON menu_items(name);

CREATE INDEX IF NOT EXISTS idx_reservations_slot
    ON reservations(restaurant_id, date, time);

CREATE INDEX IF NOT EXISTS idx_reservations_user
    ON reservations(user_id);

CREATE TABLE IF NOT EXISTS memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tier membership_tier NOT NULL DEFAULT 'basic',
    status membership_status NOT NULL DEFAULT 'active',
    start_date DATE NOT NULL DEFAULT CURRENT_DATE,
    end_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memberships_user
    ON memberships(user_id);

CREATE INDEX IF NOT EXISTS idx_memberships_status
    ON memberships(user_id, status);

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NOT NULL,
    summary TEXT NOT NULL,
    extracted_facts JSONB NOT NULL DEFAULT '{}',
    embedding vector(1024),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content JSONB NOT NULL,
    seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_time
    ON sessions(user_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_sessions_embedding
    ON sessions USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_session_messages_session
    ON session_messages(session_id, seq);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'recall_reader'
    ) THEN
        CREATE ROLE recall_reader LOGIN PASSWORD 'recall_reader';
    END IF;
END
$$;

ALTER ROLE recall_reader SET default_transaction_read_only = on;
ALTER ROLE recall_reader SET statement_timeout = '2000ms';

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM recall_reader;
GRANT  USAGE  ON SCHEMA public TO recall_reader;
GRANT  SELECT ON sessions TO recall_reader;
