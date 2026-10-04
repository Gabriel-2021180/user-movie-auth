-- =====================================================================
-- v2 recomendaciones: caché temporal de TMDB, descartes ("no me interesa")
-- y señales del usuario para el recomendador. Solo cambios aditivos.
-- =====================================================================

-- Caché de respuestas de TMDB (los términos de TMDB exigen que sea temporal)
CREATE TABLE IF NOT EXISTS tmdb_cache (
    cache_key  varchar(300) PRIMARY KEY,
    payload    jsonb NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS tmdb_cache_expires_idx ON tmdb_cache (expires_at);

CREATE TABLE IF NOT EXISTS recommendation_dismissal (
    user_id    uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    movie_id   varchar(20) NOT NULL,
    reason     varchar(20) NOT NULL CHECK (reason IN ('not_interested', 'already_seen')),
    genre_ids  integer[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, movie_id)
);

-- ---------- Caché TMDB ----------
CREATE OR REPLACE FUNCTION api.tmdb_cache_get(p_key text)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT c.payload FROM tmdb_cache c WHERE c.cache_key = p_key AND c.expires_at > now();
$$;

CREATE OR REPLACE FUNCTION api.tmdb_cache_put(p_key text, p_payload jsonb, p_ttl_seconds integer)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    INSERT INTO tmdb_cache (cache_key, payload, expires_at)
    VALUES (left(p_key, 300), p_payload, now() + make_interval(secs => p_ttl_seconds))
    ON CONFLICT (cache_key) DO UPDATE SET payload = EXCLUDED.payload, expires_at = EXCLUDED.expires_at;
$$;

-- ---------- Descartes ----------
CREATE OR REPLACE FUNCTION api.dismiss_add(p_user_id uuid, p_movie_id text, p_reason text, p_genre_ids integer[])
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    INSERT INTO recommendation_dismissal (user_id, movie_id, reason, genre_ids)
    VALUES (p_user_id, p_movie_id, p_reason, coalesce(p_genre_ids, '{}'))
    ON CONFLICT (user_id, movie_id) DO UPDATE
        SET reason = EXCLUDED.reason, genre_ids = EXCLUDED.genre_ids, created_at = now();
$$;

CREATE OR REPLACE FUNCTION api.dismiss_remove(p_user_id uuid, p_movie_id text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    DELETE FROM recommendation_dismissal d WHERE d.user_id = p_user_id AND d.movie_id = p_movie_id;
$$;

-- ---------- Señales del usuario (todo lo que usa el recomendador, en una llamada) ----------
CREATE OR REPLACE FUNCTION api.reco_signals(p_user_id uuid)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT jsonb_build_object(
        'genres', to_jsonb(u.favorite_genres),
        'favorites', coalesce((SELECT jsonb_agg(jsonb_build_object('movie_id', f.movie_id, 'title', f.title)
                                ORDER BY f.added_at DESC)
                               FROM favorite f WHERE f.user_id = u.id AND f.status), '[]'::jsonb),
        'seeds', coalesce((SELECT jsonb_agg(jsonb_build_object('movie_id', s.movie_id, 'title', s.title)
                            ORDER BY s.created_at DESC)
                           FROM user_seed_movie s WHERE s.user_id = u.id), '[]'::jsonb),
        'reviews', coalesce((SELECT jsonb_agg(jsonb_build_object('movie_id', r.movie_id, 'title', m.title, 'rating', r.rating)
                              ORDER BY r.created_at DESC)
                             FROM review r LEFT JOIN movie m ON m.id = r.movie_id
                             WHERE r.user_id = u.id), '[]'::jsonb),
        'watched', coalesce((SELECT jsonb_agg(jsonb_build_object('movie_id', w.movie_id, 'title', w.title)
                              ORDER BY w.watched_at DESC)
                             FROM watched_item w WHERE w.user_id = u.id), '[]'::jsonb),
        'watchlist', coalesce((SELECT jsonb_agg(w.movie_id) FROM watchlist_item w WHERE w.user_id = u.id), '[]'::jsonb),
        'people', coalesce((SELECT jsonb_agg(jsonb_build_object('person_id', p.person_id, 'name', p.name)
                             ORDER BY p.created_at DESC)
                            FROM favoriteperson p WHERE p.user_id = u.id), '[]'::jsonb),
        'dismissed', coalesce((SELECT jsonb_agg(jsonb_build_object('movie_id', d.movie_id, 'reason', d.reason, 'genre_ids', d.genre_ids))
                               FROM recommendation_dismissal d WHERE d.user_id = u.id), '[]'::jsonb)
    )
    FROM "user" u
    WHERE u.id = p_user_id;
$$;

-- ---------- movie_state: "dismissed" real (cambia columnas: se recrea) ----------
DROP FUNCTION IF EXISTS api.movie_state(uuid, text);
CREATE FUNCTION api.movie_state(p_user_id uuid, p_movie_id text)
RETURNS TABLE (is_favorite boolean, in_watchlist boolean, watched_at timestamptz,
               review_id uuid, in_lists uuid[], dismissed boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT
        EXISTS (SELECT 1 FROM favorite f WHERE f.user_id = p_user_id AND f.movie_id = p_movie_id AND f.status),
        EXISTS (SELECT 1 FROM watchlist_item w WHERE w.user_id = p_user_id AND w.movie_id = p_movie_id),
        (SELECT w.watched_at FROM watched_item w WHERE w.user_id = p_user_id AND w.movie_id = p_movie_id),
        (SELECT r.id FROM review r WHERE r.user_id = p_user_id AND r.movie_id = p_movie_id LIMIT 1),
        coalesce((SELECT array_agg(i.list_id ORDER BY i.list_id)
                  FROM user_list_item i JOIN user_list l ON l.id = i.list_id
                  WHERE l.user_id = p_user_id AND i.movie_id = p_movie_id), '{}'::uuid[]),
        EXISTS (SELECT 1 FROM recommendation_dismissal d WHERE d.user_id = p_user_id AND d.movie_id = p_movie_id);
$$;

-- ---------- Purga: también limpia la caché vencida de TMDB ----------
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

    RETURN QUERY SELECT v_users, v_sessions, v_codes;
END
$$;

-- Permisos explícitos
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA api FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA api TO movie_api_runtime;
REVOKE EXECUTE ON FUNCTION api._consume_code(text, text, bytea, integer) FROM movie_api_runtime;
REVOKE EXECUTE ON FUNCTION api._sentiment(integer) FROM movie_api_runtime;
