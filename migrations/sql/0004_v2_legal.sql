-- =====================================================================
-- v2 legal: exportación de datos, purga de cuentas dadas de baja y
-- retención de registros de seguridad. Solo cambios aditivos.
-- =====================================================================

-- Las reseñas se anonimizan (user_id NULL) al borrar definitivamente una cuenta
ALTER TABLE review ALTER COLUMN user_id DROP NOT NULL;

-- ---------- Reseñas: mostrar las anonimizadas como "Usuario eliminado" ----------
CREATE OR REPLACE FUNCTION api.review_list_by_movie(
    p_movie_id text, p_cursor_ts timestamptz, p_cursor_id text, p_limit integer
)
RETURNS TABLE (id uuid, user_id uuid, username text, movie_id text, movie_title text, movie_poster text,
               rating integer, content text, sentiment text, created_at timestamptz, updated_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT r.id, r.user_id, coalesce(u.username::text, 'Usuario eliminado'), r.movie_id::text,
           m.title::text, m.poster::text, r.rating, r.content::text, r.sentiment::text,
           r.created_at AT TIME ZONE 'utc', r.updated_at AT TIME ZONE 'utc'
    FROM review r
    LEFT JOIN "user" u ON u.id = r.user_id
    LEFT JOIN movie m ON m.id = r.movie_id
    WHERE r.movie_id = p_movie_id
      AND (r.user_id IS NULL OR (u.account_status = 'active' AND u.status))
      AND (p_cursor_ts IS NULL OR (r.created_at AT TIME ZONE 'utc', r.id::text) < (p_cursor_ts, p_cursor_id))
    ORDER BY r.created_at DESC, r.id DESC
    LIMIT p_limit;
$$;

CREATE OR REPLACE FUNCTION api.review_movie_summary(p_movie_id text)
RETURNS TABLE (review_count bigint, avg_rating numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT count(*), round(avg(r.rating)::numeric, 2)
    FROM review r LEFT JOIN "user" u ON u.id = r.user_id
    WHERE r.movie_id = p_movie_id
      AND (r.user_id IS NULL OR (u.account_status = 'active' AND u.status));
$$;

CREATE OR REPLACE FUNCTION api.review_get(p_review_id uuid)
RETURNS TABLE (id uuid, user_id uuid, username text, movie_id text, movie_title text, movie_poster text,
               rating integer, content text, sentiment text, created_at timestamptz, updated_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT r.id, r.user_id, coalesce(u.username::text, 'Usuario eliminado'), r.movie_id::text,
           m.title::text, m.poster::text, r.rating, r.content::text, r.sentiment::text,
           r.created_at AT TIME ZONE 'utc', r.updated_at AT TIME ZONE 'utc'
    FROM review r
    LEFT JOIN "user" u ON u.id = r.user_id
    LEFT JOIN movie m ON m.id = r.movie_id
    WHERE r.id = p_review_id;
$$;

-- ---------- Exportación de datos del usuario (derecho de acceso / portabilidad) ----------
CREATE OR REPLACE FUNCTION api.user_export(p_user_id uuid)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT jsonb_build_object(
        'profile', jsonb_build_object(
            'id', u.id, 'email', u.email, 'username', u.username,
            'first_name', u.first_name, 'last_name', u.last_name, 'bio', u.bio,
            'banner_color', u.banner_color, 'favorite_genres', u.favorite_genres,
            'onboarding_completed', u.onboarding_completed, 'account_status', u.account_status,
            'created_at', u.created_at AT TIME ZONE 'utc', 'last_profile_update', u.last_profile_update AT TIME ZONE 'utc',
            'password_changed_at', u.password_changed_at
        ),
        'consents', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'terms_version', c.terms_version, 'privacy_version', c.privacy_version,
                'accepted_at', c.accepted_at, 'ip', c.ip) ORDER BY c.accepted_at)
            FROM user_consent c WHERE c.user_id = u.id), '[]'::jsonb),
        'favorites', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'movie_id', f.movie_id, 'title', f.title, 'poster', f.poster, 'year', f.year,
                'added_at', f.added_at AT TIME ZONE 'utc') ORDER BY f.added_at)
            FROM favorite f WHERE f.user_id = u.id), '[]'::jsonb),
        'favorite_people', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'person_id', p.person_id, 'name', p.name, 'job', p.job,
                'created_at', p.created_at AT TIME ZONE 'utc') ORDER BY p.created_at)
            FROM favoriteperson p WHERE p.user_id = u.id), '[]'::jsonb),
        'reviews', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'movie_id', r.movie_id, 'rating', r.rating, 'content', r.content,
                'created_at', r.created_at AT TIME ZONE 'utc', 'updated_at', r.updated_at AT TIME ZONE 'utc')
                ORDER BY r.created_at)
            FROM review r WHERE r.user_id = u.id), '[]'::jsonb),
        'watchlist', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'movie_id', w.movie_id, 'title', w.title, 'added_at', w.added_at) ORDER BY w.added_at)
            FROM watchlist_item w WHERE w.user_id = u.id), '[]'::jsonb),
        'watched', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'movie_id', w.movie_id, 'title', w.title, 'watched_at', w.watched_at) ORDER BY w.watched_at)
            FROM watched_item w WHERE w.user_id = u.id), '[]'::jsonb),
        'lists', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'name', l.name, 'description', l.description, 'is_public', l.is_public,
                'created_at', l.created_at,
                'items', coalesce((SELECT jsonb_agg(jsonb_build_object(
                        'movie_id', i.movie_id, 'title', i.title, 'added_at', i.added_at) ORDER BY i.added_at)
                    FROM user_list_item i WHERE i.list_id = l.id), '[]'::jsonb)) ORDER BY l.created_at)
            FROM user_list l WHERE l.user_id = u.id), '[]'::jsonb),
        'onboarding_seed_movies', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'movie_id', s.movie_id, 'title', s.title) ORDER BY s.created_at)
            FROM user_seed_movie s WHERE s.user_id = u.id), '[]'::jsonb),
        'sessions', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'created_at', t.created_at, 'expires_at', t.expires_at, 'revoked_at', t.revoked_at,
                'ip', t.ip, 'user_agent', t.user_agent) ORDER BY t.created_at)
            FROM refresh_token t WHERE t.user_id = u.id), '[]'::jsonb)
    )
    FROM "user" u
    WHERE u.id = p_user_id;
$$;

-- ---------- Purga diaria ----------
-- 1) Cuentas dadas de baja hace más de p_grace_days: se borran sus datos y sus reseñas
--    quedan anonimizadas.
-- 2) Sesiones (IP / navegador): se borran p_session_retention_days después de vencer o cerrarse.
-- 3) Códigos vencidos (y los registros temporales heredados de v1) se borran a diario.
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
        -- refresh_token, user_consent, listas, vistas, watchlist y semillas: ON DELETE CASCADE
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

    RETURN QUERY SELECT v_users, v_sessions, v_codes;
END
$$;

-- Permisos explícitos
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA api FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA api TO movie_api_runtime;
REVOKE EXECUTE ON FUNCTION api._consume_code(text, text, bytea, integer) FROM movie_api_runtime;
REVOKE EXECUTE ON FUNCTION api._sentiment(integer) FROM movie_api_runtime;
