-- =====================================================================
-- v2 auth: esquema api (solo funciones), tablas nuevas y rol runtime.
-- Solo cambios aditivos: v1 sigue funcionando sobre las tablas existentes.
-- =====================================================================

-- ---------- Rol de la aplicación (mínimos privilegios) ----------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'movie_api_runtime') THEN
        -- Se crea sin login; scripts/create_runtime_role.py le asigna contraseña y LOGIN
        CREATE ROLE movie_api_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

ALTER ROLE movie_api_runtime SET search_path = api;
ALTER ROLE movie_api_runtime SET statement_timeout = '10s';
ALTER ROLE movie_api_runtime SET idle_in_transaction_session_timeout = '30s';

-- Sin acceso a tablas ni a public: todo pasa por funciones del esquema api
REVOKE ALL ON SCHEMA public FROM movie_api_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM movie_api_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM movie_api_runtime;

CREATE SCHEMA IF NOT EXISTS api;
REVOKE ALL ON SCHEMA api FROM PUBLIC;
GRANT USAGE ON SCHEMA api TO movie_api_runtime;
-- Por defecto Postgres da EXECUTE a PUBLIC en funciones nuevas: lo quitamos
ALTER DEFAULT PRIVILEGES IN SCHEMA api REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT EXECUTE ON FUNCTIONS TO movie_api_runtime;

-- ---------- Columnas nuevas en "user" (con default: v1 no se entera) ----------
ALTER TABLE "user"
    ADD COLUMN IF NOT EXISTS bio varchar(280),
    ADD COLUMN IF NOT EXISTS favorite_genres integer[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS onboarding_completed boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS account_status varchar(16) NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS deactivated_at timestamptz,
    ADD COLUMN IF NOT EXISTS password_changed_at timestamptz;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_account_status_chk') THEN
        ALTER TABLE "user" ADD CONSTRAINT user_account_status_chk
            CHECK (account_status IN ('active', 'deactivated'));
    END IF;
END
$$;

-- Unicidad sin distinguir mayúsculas (si hubiera duplicados la migración falla y no aplica nada)
CREATE UNIQUE INDEX IF NOT EXISTS user_email_lower_uq ON "user" (lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS user_username_lower_uq ON "user" (lower(username));
CREATE INDEX IF NOT EXISTS favorite_user_idx ON favorite (user_id);
CREATE INDEX IF NOT EXISTS review_user_idx ON review (user_id);
CREATE INDEX IF NOT EXISTS review_movie_idx ON review (movie_id);

-- ---------- Tablas nuevas ----------
CREATE TABLE IF NOT EXISTS refresh_token (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    family_id   uuid NOT NULL,
    token_hash  bytea NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    revoked_at  timestamptz,
    replaced_by uuid,
    user_agent  varchar(256),
    ip          varchar(64)
);
CREATE INDEX IF NOT EXISTS refresh_token_user_idx ON refresh_token (user_id);
CREATE INDEX IF NOT EXISTS refresh_token_family_idx ON refresh_token (family_id);

CREATE TABLE IF NOT EXISTS verification_code (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    purpose    varchar(16) NOT NULL CHECK (purpose IN ('signup', 'password_reset')),
    email      varchar(254) NOT NULL,          -- siempre en minúsculas
    code_hash  bytea NOT NULL,                 -- HMAC-SHA256, nunca el código en claro
    payload    jsonb,                          -- datos del registro pendiente
    attempts   integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    UNIQUE (purpose, email)
);

CREATE TABLE IF NOT EXISTS user_consent (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    terms_version   varchar(32) NOT NULL,
    privacy_version varchar(32) NOT NULL,
    accepted_at     timestamptz NOT NULL DEFAULT now(),
    ip              varchar(64)
);
CREATE INDEX IF NOT EXISTS user_consent_user_idx ON user_consent (user_id, accepted_at DESC);

-- =====================================================================
-- Funciones (SECURITY DEFINER + search_path fijo)
-- =====================================================================

-- Perfil del usuario autenticado
CREATE OR REPLACE FUNCTION api.user_me(p_user_id uuid)
RETURNS TABLE (
    id uuid, email text, username text, first_name text, last_name text, bio text,
    banner_color text, favorite_genres integer[], onboarding_completed boolean,
    account_status text, is_enabled boolean, created_at timestamp,
    password_changed_at timestamptz, terms_version text, privacy_version text,
    favorites_count bigint, reviews_count bigint, avg_rating numeric
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT u.id, u.email::text, u.username::text, u.first_name::text, u.last_name::text, u.bio::text,
           u.banner_color::text, u.favorite_genres, u.onboarding_completed,
           u.account_status::text, u.status, u.created_at,
           u.password_changed_at, c.terms_version::text, c.privacy_version::text,
           (SELECT count(*) FROM favorite f WHERE f.user_id = u.id AND f.status),
           (SELECT count(*) FROM review r WHERE r.user_id = u.id),
           (SELECT round(avg(r.rating)::numeric, 2) FROM review r WHERE r.user_id = u.id)
    FROM "user" u
    LEFT JOIN LATERAL (
        SELECT uc.terms_version, uc.privacy_version
        FROM user_consent uc
        WHERE uc.user_id = u.id
        ORDER BY uc.accepted_at DESC
        LIMIT 1
    ) c ON true
    WHERE u.id = p_user_id;
$$;

-- Datos para autenticar (por email o por id)
CREATE OR REPLACE FUNCTION api.user_auth_by_email(p_email text)
RETURNS TABLE (
    id uuid, username text, hashed_password text, is_enabled boolean, account_status text,
    deactivated_at timestamptz, locked_until timestamp
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT u.id, u.username::text, u.hashed_password::text, u.status, u.account_status::text,
           u.deactivated_at, u.locked_until
    FROM "user" u
    WHERE lower(u.email) = lower(p_email);
$$;

CREATE OR REPLACE FUNCTION api.user_auth_by_id(p_user_id uuid)
RETURNS TABLE (
    id uuid, username text, hashed_password text, is_enabled boolean, account_status text,
    deactivated_at timestamptz, locked_until timestamp
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT u.id, u.username::text, u.hashed_password::text, u.status, u.account_status::text,
           u.deactivated_at, u.locked_until
    FROM "user" u
    WHERE u.id = p_user_id;
$$;

-- Intento fallido: bloqueo progresivo 4 -> 5 min, 5 -> 15 min, 6+ -> 60 min
CREATE OR REPLACE FUNCTION api.login_register_failure(p_user_id uuid)
RETURNS TABLE (failed_attempts integer, locked_until timestamp)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_attempts integer;
    v_lock timestamp;
BEGIN
    UPDATE "user" u
    SET failed_login_attempts = coalesce(u.failed_login_attempts, 0) + 1
    WHERE u.id = p_user_id
    RETURNING u.failed_login_attempts INTO v_attempts;

    IF v_attempts IS NULL THEN
        RETURN;
    END IF;

    v_lock := CASE
        WHEN v_attempts >= 6 THEN (now() AT TIME ZONE 'utc') + interval '60 minutes'
        WHEN v_attempts = 5 THEN (now() AT TIME ZONE 'utc') + interval '15 minutes'
        WHEN v_attempts = 4 THEN (now() AT TIME ZONE 'utc') + interval '5 minutes'
    END;

    IF v_lock IS NOT NULL THEN
        UPDATE "user" u SET locked_until = v_lock WHERE u.id = p_user_id;
    END IF;

    RETURN QUERY SELECT v_attempts, v_lock;
END
$$;

-- Login correcto: limpia contadores y (opcional) migra el hash a argon2
CREATE OR REPLACE FUNCTION api.login_register_success(p_user_id uuid, p_new_hash text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    UPDATE "user" u
    SET failed_login_attempts = 0,
        locked_until = NULL,
        hashed_password = coalesce(p_new_hash, u.hashed_password)
    WHERE u.id = p_user_id;
$$;

-- Registro paso 1: guarda el código (hash) y los datos pendientes
-- Estados: ok | email_taken | username_taken | too_soon
CREATE OR REPLACE FUNCTION api.signup_start(
    p_email text, p_username text, p_code_hash bytea, p_payload jsonb, p_ttl_minutes integer
)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_email text := lower(p_email);
BEGIN
    IF EXISTS (SELECT 1 FROM "user" u WHERE lower(u.username) = lower(p_username)) THEN
        RETURN 'username_taken';
    END IF;
    IF EXISTS (SELECT 1 FROM "user" u WHERE lower(u.email) = v_email) THEN
        RETURN 'email_taken';
    END IF;
    IF EXISTS (SELECT 1 FROM verification_code v
               WHERE v.purpose = 'signup' AND v.email = v_email
                 AND v.created_at > now() - interval '60 seconds') THEN
        RETURN 'too_soon';
    END IF;

    INSERT INTO verification_code (purpose, email, code_hash, payload, attempts, created_at, expires_at)
    VALUES ('signup', v_email, p_code_hash, p_payload, 0, now(), now() + make_interval(mins => p_ttl_minutes))
    ON CONFLICT (purpose, email) DO UPDATE
        SET code_hash = EXCLUDED.code_hash,
            payload = EXCLUDED.payload,
            attempts = 0,
            created_at = EXCLUDED.created_at,
            expires_at = EXCLUDED.expires_at;
    RETURN 'ok';
END
$$;

-- Valida un código. Estados: ok | not_found | expired | too_many_attempts | invalid_code
-- Devuelve el payload cuando es ok y borra el código (uso único).
CREATE OR REPLACE FUNCTION api._consume_code(
    p_purpose text, p_email text, p_code_hash bytea, p_max_attempts integer
)
RETURNS TABLE (status text, payload jsonb)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v verification_code%ROWTYPE;
BEGIN
    SELECT * INTO v FROM verification_code vc
    WHERE vc.purpose = p_purpose AND vc.email = lower(p_email)
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'not_found'::text, NULL::jsonb; RETURN;
    END IF;
    IF v.expires_at < now() THEN
        DELETE FROM verification_code vc WHERE vc.id = v.id;
        RETURN QUERY SELECT 'expired'::text, NULL::jsonb; RETURN;
    END IF;
    IF v.attempts >= p_max_attempts THEN
        DELETE FROM verification_code vc WHERE vc.id = v.id;
        RETURN QUERY SELECT 'too_many_attempts'::text, NULL::jsonb; RETURN;
    END IF;
    IF v.code_hash <> p_code_hash THEN
        UPDATE verification_code vc SET attempts = vc.attempts + 1 WHERE vc.id = v.id;
        RETURN QUERY SELECT 'invalid_code'::text, NULL::jsonb; RETURN;
    END IF;

    DELETE FROM verification_code vc WHERE vc.id = v.id;
    RETURN QUERY SELECT 'ok'::text, v.payload;
END
$$;
-- Función interna: no se expone al rol runtime
REVOKE EXECUTE ON FUNCTION api._consume_code(text, text, bytea, integer) FROM movie_api_runtime;

-- Registro paso 2: valida el código, crea el usuario y guarda el consentimiento
-- Estados: los de _consume_code + already_registered
CREATE OR REPLACE FUNCTION api.signup_complete(
    p_email text, p_code_hash bytea, p_max_attempts integer,
    p_terms_version text, p_privacy_version text, p_ip text
)
RETURNS TABLE (status text, user_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_status text;
    v_payload jsonb;
    v_user_id uuid;
BEGIN
    SELECT c.status, c.payload INTO v_status, v_payload
    FROM api._consume_code('signup', p_email, p_code_hash, p_max_attempts) c;

    IF v_status <> 'ok' THEN
        RETURN QUERY SELECT v_status, NULL::uuid; RETURN;
    END IF;

    BEGIN
        INSERT INTO "user" (
            id, first_name, last_name, username, email, hashed_password, created_at, status,
            banner_color, daily_color_changes, failed_login_attempts, password_changed_at
        ) VALUES (
            gen_random_uuid(), v_payload->>'first_name', v_payload->>'last_name',
            v_payload->>'username', lower(p_email), v_payload->>'hashed_password',
            now() AT TIME ZONE 'utc', true, '#a16207', 0, 0, now()
        )
        RETURNING "user".id INTO v_user_id;
    EXCEPTION WHEN unique_violation THEN
        RETURN QUERY SELECT 'already_registered'::text, NULL::uuid; RETURN;
    END;

    INSERT INTO user_consent (user_id, terms_version, privacy_version, ip)
    VALUES (v_user_id, p_terms_version, p_privacy_version, p_ip);

    RETURN QUERY SELECT 'ok'::text, v_user_id;
END
$$;

-- Olvidé mi contraseña paso 1. Estados: ok | no_user | too_soon
CREATE OR REPLACE FUNCTION api.password_reset_start(p_email text, p_code_hash bytea, p_ttl_minutes integer)
RETURNS TABLE (status text, username text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_email text := lower(p_email);
    v_username text;
BEGIN
    SELECT u.username INTO v_username FROM "user" u
    WHERE lower(u.email) = v_email AND u.account_status = 'active' AND u.status;

    IF v_username IS NULL THEN
        RETURN QUERY SELECT 'no_user'::text, NULL::text; RETURN;
    END IF;
    IF EXISTS (SELECT 1 FROM verification_code v
               WHERE v.purpose = 'password_reset' AND v.email = v_email
                 AND v.created_at > now() - interval '60 seconds') THEN
        RETURN QUERY SELECT 'too_soon'::text, NULL::text; RETURN;
    END IF;

    INSERT INTO verification_code (purpose, email, code_hash, attempts, created_at, expires_at)
    VALUES ('password_reset', v_email, p_code_hash, 0, now(), now() + make_interval(mins => p_ttl_minutes))
    ON CONFLICT (purpose, email) DO UPDATE
        SET code_hash = EXCLUDED.code_hash,
            payload = NULL,
            attempts = 0,
            created_at = EXCLUDED.created_at,
            expires_at = EXCLUDED.expires_at;

    RETURN QUERY SELECT 'ok'::text, v_username;
END
$$;

-- Olvidé mi contraseña paso 2: cambia el hash, desbloquea y revoca todas las sesiones
CREATE OR REPLACE FUNCTION api.password_reset_complete(
    p_email text, p_code_hash bytea, p_max_attempts integer, p_new_hash text
)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_status text;
    v_user_id uuid;
BEGIN
    SELECT c.status INTO v_status
    FROM api._consume_code('password_reset', p_email, p_code_hash, p_max_attempts) c;

    IF v_status <> 'ok' THEN
        RETURN v_status;
    END IF;

    UPDATE "user" u
    SET hashed_password = p_new_hash,
        password_changed_at = now(),
        failed_login_attempts = 0,
        locked_until = NULL
    WHERE lower(u.email) = lower(p_email)
    RETURNING u.id INTO v_user_id;

    IF v_user_id IS NULL THEN
        RETURN 'not_found';
    END IF;

    UPDATE refresh_token t SET revoked_at = now()
    WHERE t.user_id = v_user_id AND t.revoked_at IS NULL;
    RETURN 'ok';
END
$$;

-- Emite un refresh token (p_family_id NULL = sesión nueva)
CREATE OR REPLACE FUNCTION api.refresh_issue(
    p_user_id uuid, p_family_id uuid, p_token_hash bytea, p_ttl_seconds integer,
    p_user_agent text, p_ip text
)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    INSERT INTO refresh_token (user_id, family_id, token_hash, expires_at, user_agent, ip)
    VALUES (p_user_id, coalesce(p_family_id, gen_random_uuid()), p_token_hash,
            now() + make_interval(secs => p_ttl_seconds), left(p_user_agent, 256), left(p_ip, 64));
$$;

-- Rotación. Estados: ok | invalid | expired | reused | user_disabled
-- Si se reusa un token ya rotado se revoca toda la familia (posible robo).
CREATE OR REPLACE FUNCTION api.refresh_rotate(
    p_old_hash bytea, p_new_hash bytea, p_ttl_seconds integer, p_user_agent text, p_ip text
)
RETURNS TABLE (status text, user_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    t refresh_token%ROWTYPE;
    v_new_id uuid;
BEGIN
    SELECT * INTO t FROM refresh_token rt WHERE rt.token_hash = p_old_hash FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'invalid'::text, NULL::uuid; RETURN;
    END IF;
    IF t.revoked_at IS NOT NULL THEN
        UPDATE refresh_token rt SET revoked_at = now()
        WHERE rt.family_id = t.family_id AND rt.revoked_at IS NULL;
        RETURN QUERY SELECT 'reused'::text, t.user_id; RETURN;
    END IF;
    IF t.expires_at < now() THEN
        UPDATE refresh_token rt SET revoked_at = now() WHERE rt.id = t.id;
        RETURN QUERY SELECT 'expired'::text, t.user_id; RETURN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM "user" u
                   WHERE u.id = t.user_id AND u.status AND u.account_status = 'active') THEN
        UPDATE refresh_token rt SET revoked_at = now()
        WHERE rt.user_id = t.user_id AND rt.revoked_at IS NULL;
        RETURN QUERY SELECT 'user_disabled'::text, t.user_id; RETURN;
    END IF;

    INSERT INTO refresh_token (user_id, family_id, token_hash, expires_at, user_agent, ip)
    VALUES (t.user_id, t.family_id, p_new_hash, now() + make_interval(secs => p_ttl_seconds),
            left(p_user_agent, 256), left(p_ip, 64))
    RETURNING refresh_token.id INTO v_new_id;

    UPDATE refresh_token rt SET revoked_at = now(), replaced_by = v_new_id WHERE rt.id = t.id;
    RETURN QUERY SELECT 'ok'::text, t.user_id;
END
$$;

-- Logout de un dispositivo: revoca la familia del token
CREATE OR REPLACE FUNCTION api.refresh_revoke(p_token_hash bytea)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    UPDATE refresh_token rt SET revoked_at = now()
    WHERE rt.revoked_at IS NULL
      AND rt.family_id = (SELECT x.family_id FROM refresh_token x WHERE x.token_hash = p_token_hash);
$$;

-- Logout de todos los dispositivos
CREATE OR REPLACE FUNCTION api.refresh_revoke_all(p_user_id uuid)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    UPDATE refresh_token rt SET revoked_at = now()
    WHERE rt.user_id = p_user_id AND rt.revoked_at IS NULL;
$$;

-- Baja de cuenta (reactivable durante el plazo de gracia)
CREATE OR REPLACE FUNCTION api.user_deactivate(p_user_id uuid)
RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_at timestamptz;
BEGIN
    UPDATE "user" u
    SET account_status = 'deactivated', deactivated_at = now()
    WHERE u.id = p_user_id AND u.account_status = 'active'
    RETURNING u.deactivated_at INTO v_at;

    UPDATE refresh_token rt SET revoked_at = now()
    WHERE rt.user_id = p_user_id AND rt.revoked_at IS NULL;
    RETURN v_at;
END
$$;

-- Reactivación. Estados: ok | not_deactivated | expired
CREATE OR REPLACE FUNCTION api.user_reactivate(p_user_id uuid, p_grace_days integer)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_status text;
    v_at timestamptz;
BEGIN
    SELECT u.account_status, u.deactivated_at INTO v_status, v_at
    FROM "user" u WHERE u.id = p_user_id FOR UPDATE;

    IF v_status IS DISTINCT FROM 'deactivated' THEN
        RETURN 'not_deactivated';
    END IF;
    IF v_at + make_interval(days => p_grace_days) < now() THEN
        RETURN 'expired';
    END IF;

    UPDATE "user" u
    SET account_status = 'active', deactivated_at = NULL, failed_login_attempts = 0, locked_until = NULL
    WHERE u.id = p_user_id;
    RETURN 'ok';
END
$$;

-- Aceptación de Términos / Privacidad
CREATE OR REPLACE FUNCTION api.consent_record(
    p_user_id uuid, p_terms_version text, p_privacy_version text, p_ip text
)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    INSERT INTO user_consent (user_id, terms_version, privacy_version, ip)
    VALUES (p_user_id, p_terms_version, p_privacy_version, left(p_ip, 64));
$$;

-- Permisos explícitos (además de los default privileges)
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA api FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA api TO movie_api_runtime;
REVOKE EXECUTE ON FUNCTION api._consume_code(text, text, bytea, integer) FROM movie_api_runtime;
