-- v2: límite de solicitudes compartido entre instancias y bloqueo de login por email
-- (exista o no la cuenta, para no revelar qué emails están registrados).
-- Las claves son HMAC calculados en la API: aquí nunca se guarda una IP ni un email en claro.

-- ---------- Límite de solicitudes (ventana fija) ----------
CREATE TABLE IF NOT EXISTS rate_limit (
    key bytea NOT NULL,
    window_start timestamptz NOT NULL,
    hits integer NOT NULL,
    PRIMARY KEY (key, window_start)
);

-- Suma un intento a la ventana actual. allowed = false si se pasó del máximo.
CREATE OR REPLACE FUNCTION api.rate_limit_hit(p_key bytea, p_window_seconds integer, p_max integer)
RETURNS TABLE (allowed boolean, retry_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_start timestamptz := to_timestamp(floor(extract(epoch FROM now()) / p_window_seconds) * p_window_seconds);
    v_hits integer;
BEGIN
    INSERT INTO rate_limit AS r (key, window_start, hits)
    VALUES (p_key, v_start, 1)
    ON CONFLICT (key, window_start) DO UPDATE SET hits = r.hits + 1
    RETURNING r.hits INTO v_hits;

    RETURN QUERY SELECT
        v_hits <= p_max,
        greatest(1, ceil(extract(epoch FROM (v_start + make_interval(secs => p_window_seconds) - now()))))::integer;
END
$$;

-- ---------- Bloqueo de login por email ----------
CREATE TABLE IF NOT EXISTS login_throttle (
    email_key bytea PRIMARY KEY,
    failures integer NOT NULL DEFAULT 0,
    locked_until timestamptz,
    last_failure_at timestamptz NOT NULL DEFAULT now()
);

-- Espera tras cada fallo: 3 intentos libres y luego 5, 15, 30 min, 1, 2, 4, 8 h y 24 h como tope
CREATE OR REPLACE FUNCTION api._lock_minutes(p_failures integer)
RETURNS integer
LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp
AS $$
    SELECT CASE
        WHEN p_failures <= 3 THEN 0
        WHEN p_failures = 4 THEN 5
        WHEN p_failures = 5 THEN 15
        WHEN p_failures = 6 THEN 30
        WHEN p_failures = 7 THEN 60
        WHEN p_failures = 8 THEN 120
        WHEN p_failures = 9 THEN 240
        WHEN p_failures = 10 THEN 480
        ELSE 1440
    END;
$$;

-- Estado actual (sin modificarlo). Un historial viejo (24 h sin fallos ni bloqueo) ya no cuenta.
CREATE OR REPLACE FUNCTION api.login_throttle_status(p_email_key bytea)
RETURNS TABLE (failures integer, locked_until timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT CASE WHEN greatest(t.last_failure_at, coalesce(t.locked_until, t.last_failure_at)) < now() - interval '24 hours'
                THEN 0 ELSE t.failures END,
           CASE WHEN t.locked_until > now() THEN t.locked_until END
    FROM login_throttle t
    WHERE t.email_key = p_email_key;
$$;

-- Registra un fallo y devuelve el nuevo estado (locked_until es null si todavía no toca bloquear)
CREATE OR REPLACE FUNCTION api.login_throttle_fail(p_email_key bytea)
RETURNS TABLE (failures integer, locked_until timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_failures integer;
    v_lock timestamptz;
BEGIN
    INSERT INTO login_throttle AS t (email_key, failures, last_failure_at)
    VALUES (p_email_key, 1, now())
    ON CONFLICT (email_key) DO UPDATE SET
        failures = CASE
            WHEN greatest(t.last_failure_at, coalesce(t.locked_until, t.last_failure_at)) < now() - interval '24 hours'
            THEN 1 ELSE t.failures + 1 END,
        last_failure_at = now()
    RETURNING t.failures INTO v_failures;

    IF api._lock_minutes(v_failures) > 0 THEN
        v_lock := now() + make_interval(mins => api._lock_minutes(v_failures));
        UPDATE login_throttle t SET locked_until = v_lock WHERE t.email_key = p_email_key;
    END IF;

    RETURN QUERY SELECT v_failures, v_lock;
END
$$;

CREATE OR REPLACE FUNCTION api.login_throttle_clear(p_email_key bytea)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    DELETE FROM login_throttle t WHERE t.email_key = p_email_key;
$$;

-- ---------- Purga: también limpia ventanas de límite y bloqueos viejos ----------
CREATE OR REPLACE FUNCTION api.purge_run(p_grace_days integer, p_session_retention_days integer)
RETURNS TABLE (users_purged integer, sessions_deleted integer, codes_deleted integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_users integer := 0;
    v_sessions integer := 0;
    v_codes integer := 0;
    v_n integer;
    r record;
BEGIN
    FOR r IN
        SELECT u.id, lower(u.email) AS email FROM "user" u
        WHERE u.account_status = 'deactivated'
          AND u.deactivated_at < now() - make_interval(days => p_grace_days)
        FOR UPDATE SKIP LOCKED
    LOOP
        UPDATE review SET user_id = NULL WHERE user_id = r.id;
        DELETE FROM favorite WHERE user_id = r.id;
        DELETE FROM favoriteperson WHERE user_id = r.id;
        DELETE FROM verification_code WHERE email = r.email;
        DELETE FROM passwordreset WHERE lower(email) = r.email;
        DELETE FROM pendingregistration WHERE lower(email) = r.email;
        -- refresh_token, user_consent, listas, vistas, watchlist, semillas y descartes: ON DELETE CASCADE
        DELETE FROM "user" WHERE id = r.id;
        v_users := v_users + 1;
    END LOOP;

    DELETE FROM refresh_token t
    WHERE coalesce(t.revoked_at, t.expires_at) < now() - make_interval(days => p_session_retention_days);
    GET DIAGNOSTICS v_sessions = ROW_COUNT;

    DELETE FROM verification_code v WHERE v.expires_at < now() - interval '1 day';
    GET DIAGNOSTICS v_codes = ROW_COUNT;
    DELETE FROM passwordreset p WHERE p.expires_at < (now() AT TIME ZONE 'utc') - interval '1 day';
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_codes := v_codes + v_n;
    DELETE FROM pendingregistration p WHERE p.expires_at < (now() AT TIME ZONE 'utc') - interval '1 day';
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_codes := v_codes + v_n;

    DELETE FROM tmdb_cache c WHERE c.expires_at < now();
    DELETE FROM rate_limit rl WHERE rl.window_start < now() - interval '2 days';
    DELETE FROM login_throttle lt
    WHERE greatest(lt.last_failure_at, coalesce(lt.locked_until, lt.last_failure_at)) < now() - interval '2 days';

    RETURN QUERY SELECT v_users, v_sessions, v_codes;
END
$$;

-- Permisos explícitos
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA api FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA api TO movie_api_runtime;
REVOKE EXECUTE ON FUNCTION api._consume_code(text, text, bytea, integer) FROM movie_api_runtime;
REVOKE EXECUTE ON FUNCTION api._sentiment(integer) FROM movie_api_runtime;
REVOKE EXECUTE ON FUNCTION api._lock_minutes(integer) FROM movie_api_runtime;
