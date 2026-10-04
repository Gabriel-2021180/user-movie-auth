-- =====================================================================
-- v2 perfil, onboarding, listas y acceso por funciones a favoritos,
-- personas favoritas y reseñas. Solo cambios aditivos.
-- Convención: las fechas heredadas (timestamp sin zona, en UTC) se devuelven
-- como timestamptz con "AT TIME ZONE 'utc'".
-- =====================================================================

-- ---------- Tablas nuevas ----------
CREATE TABLE IF NOT EXISTS watchlist_item (
    user_id  uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    movie_id varchar(20) NOT NULL,
    title    varchar(300) NOT NULL,
    poster   varchar(500),
    year     varchar(10),
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, movie_id)
);

CREATE TABLE IF NOT EXISTS watched_item (
    user_id    uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    movie_id   varchar(20) NOT NULL,
    title      varchar(300) NOT NULL,
    poster     varchar(500),
    year       varchar(10),
    watched_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, movie_id)
);

CREATE TABLE IF NOT EXISTS user_list (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    name        varchar(80) NOT NULL,
    description varchar(500),
    is_public   boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS user_list_name_uq ON user_list (user_id, lower(name));

CREATE TABLE IF NOT EXISTS user_list_item (
    list_id  uuid NOT NULL REFERENCES user_list(id) ON DELETE CASCADE,
    movie_id varchar(20) NOT NULL,
    title    varchar(300) NOT NULL,
    poster   varchar(500),
    year     varchar(10),
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (list_id, movie_id)
);

-- Películas semilla del onboarding (cuentan como "me gusta" para el recomendador)
CREATE TABLE IF NOT EXISTS user_seed_movie (
    user_id    uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    movie_id   varchar(20) NOT NULL,
    title      varchar(300) NOT NULL,
    poster     varchar(500),
    year       varchar(10),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, movie_id)
);

CREATE INDEX IF NOT EXISTS favoriteperson_user_idx ON favoriteperson (user_id);

-- =====================================================================
-- Perfil
-- =====================================================================

-- user_me cambia de columnas (agrega watched/watchlist): hay que recrearla
DROP FUNCTION IF EXISTS api.user_me(uuid);
CREATE FUNCTION api.user_me(p_user_id uuid)
RETURNS TABLE (
    id uuid, email text, username text, first_name text, last_name text, bio text,
    banner_color text, favorite_genres integer[], onboarding_completed boolean,
    account_status text, is_enabled boolean, created_at timestamptz,
    password_changed_at timestamptz, terms_version text, privacy_version text,
    favorites_count bigint, reviews_count bigint, avg_rating numeric,
    watched_count bigint, watchlist_count bigint
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT u.id, u.email::text, u.username::text, u.first_name::text, u.last_name::text, u.bio::text,
           u.banner_color::text, u.favorite_genres, u.onboarding_completed,
           u.account_status::text, u.status, u.created_at AT TIME ZONE 'utc',
           u.password_changed_at, c.terms_version::text, c.privacy_version::text,
           (SELECT count(*) FROM favorite f WHERE f.user_id = u.id AND f.status),
           (SELECT count(*) FROM review r WHERE r.user_id = u.id),
           (SELECT round(avg(r.rating)::numeric, 2) FROM review r WHERE r.user_id = u.id),
           (SELECT count(*) FROM watched_item w WHERE w.user_id = u.id),
           (SELECT count(*) FROM watchlist_item w WHERE w.user_id = u.id)
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

-- Perfil público (solo cuentas activas)
CREATE OR REPLACE FUNCTION api.user_public(p_username text)
RETURNS TABLE (
    username text, bio text, banner_color text, created_at timestamptz,
    favorites_count bigint, reviews_count bigint, avg_rating numeric,
    watched_count bigint, watchlist_count bigint
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT u.username::text, u.bio::text, u.banner_color::text, u.created_at AT TIME ZONE 'utc',
           (SELECT count(*) FROM favorite f WHERE f.user_id = u.id AND f.status),
           (SELECT count(*) FROM review r WHERE r.user_id = u.id),
           (SELECT round(avg(r.rating)::numeric, 2) FROM review r WHERE r.user_id = u.id),
           (SELECT count(*) FROM watched_item w WHERE w.user_id = u.id),
           (SELECT count(*) FROM watchlist_item w WHERE w.user_id = u.id)
    FROM "user" u
    WHERE lower(u.username) = lower(p_username) AND u.status AND u.account_status = 'active';
$$;

-- Edición de perfil con las reglas de v1:
--   username / nombre / apellido: una vez cada 14 días (solo si el valor cambia)
--   color del banner: máximo 3 cambios por día
-- Estados: ok | username_taken | name_change_too_soon | color_limit | not_found
CREATE OR REPLACE FUNCTION api.user_update_profile(
    p_user_id uuid, p_username text, p_first_name text, p_last_name text,
    p_set_bio boolean, p_bio text, p_banner_color text, p_favorite_genres integer[]
)
RETURNS TABLE (status text, days_left integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    u "user"%ROWTYPE;
    v_now timestamp := now() AT TIME ZONE 'utc';
    v_sensitive boolean := false;
    v_days integer;
BEGIN
    SELECT * INTO u FROM "user" x WHERE x.id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'not_found'::text, NULL::integer; RETURN;
    END IF;

    IF p_username IS NOT NULL AND p_username <> u.username THEN
        IF lower(p_username) <> lower(u.username)
           AND EXISTS (SELECT 1 FROM "user" x WHERE lower(x.username) = lower(p_username)) THEN
            RETURN QUERY SELECT 'username_taken'::text, NULL::integer; RETURN;
        END IF;
        u.username := p_username; v_sensitive := true;
    END IF;
    IF p_first_name IS NOT NULL AND p_first_name <> u.first_name THEN
        u.first_name := p_first_name; v_sensitive := true;
    END IF;
    IF p_last_name IS NOT NULL AND p_last_name <> u.last_name THEN
        u.last_name := p_last_name; v_sensitive := true;
    END IF;

    IF v_sensitive THEN
        IF u.last_profile_update IS NOT NULL THEN
            v_days := 14 - extract(day FROM v_now - u.last_profile_update)::integer;
            IF v_days > 0 THEN
                RETURN QUERY SELECT 'name_change_too_soon'::text, v_days; RETURN;
            END IF;
        END IF;
        u.last_profile_update := v_now;
    END IF;

    IF p_banner_color IS NOT NULL AND p_banner_color IS DISTINCT FROM u.banner_color THEN
        IF u.last_color_change_at IS NULL OR u.last_color_change_at::date < v_now::date THEN
            u.daily_color_changes := 0;
        END IF;
        IF coalesce(u.daily_color_changes, 0) >= 3 THEN
            RETURN QUERY SELECT 'color_limit'::text, NULL::integer; RETURN;
        END IF;
        u.banner_color := p_banner_color;
        u.daily_color_changes := coalesce(u.daily_color_changes, 0) + 1;
        u.last_color_change_at := v_now;
    END IF;

    IF p_set_bio THEN
        u.bio := p_bio;
    END IF;
    IF p_favorite_genres IS NOT NULL THEN
        u.favorite_genres := p_favorite_genres;
    END IF;

    BEGIN
        UPDATE "user" x
        SET username = u.username, first_name = u.first_name, last_name = u.last_name,
            last_profile_update = u.last_profile_update, banner_color = u.banner_color,
            daily_color_changes = u.daily_color_changes, last_color_change_at = u.last_color_change_at,
            bio = u.bio, favorite_genres = u.favorite_genres
        WHERE x.id = p_user_id;
    EXCEPTION WHEN unique_violation THEN
        RETURN QUERY SELECT 'username_taken'::text, NULL::integer; RETURN;
    END;

    RETURN QUERY SELECT 'ok'::text, NULL::integer;
END
$$;

-- Onboarding: géneros + películas semilla (reemplaza) + personas favoritas (agrega)
-- p_seed_movies: [{movie_id, title, poster, year}], p_seed_people: [{person_id, name, photo, job}]
CREATE OR REPLACE FUNCTION api.onboarding_complete(
    p_user_id uuid, p_genres integer[], p_seed_movies jsonb, p_seed_people jsonb
)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE "user" u SET favorite_genres = p_genres, onboarding_completed = true WHERE u.id = p_user_id;

    DELETE FROM user_seed_movie s WHERE s.user_id = p_user_id;
    INSERT INTO user_seed_movie (user_id, movie_id, title, poster, year)
    SELECT DISTINCT ON (m->>'movie_id') p_user_id, m->>'movie_id', m->>'title', m->>'poster', m->>'year'
    FROM jsonb_array_elements(coalesce(p_seed_movies, '[]'::jsonb)) m;

    INSERT INTO favoriteperson (id, user_id, person_id, name, photo, job, known_for, created_at)
    SELECT gen_random_uuid(), p_user_id, p->>'person_id', p->>'name', p->>'photo',
           coalesce(p->>'job', 'Acting'), NULL, now() AT TIME ZONE 'utc'
    FROM jsonb_array_elements(coalesce(p_seed_people, '[]'::jsonb)) p
    WHERE NOT EXISTS (SELECT 1 FROM favoriteperson fp
                      WHERE fp.user_id = p_user_id AND fp.person_id = p->>'person_id');
END
$$;

-- =====================================================================
-- Favoritos (películas)
-- =====================================================================

CREATE OR REPLACE FUNCTION api.favorite_list(
    p_user_id uuid, p_cursor_ts timestamptz, p_cursor_id text, p_limit integer
)
RETURNS TABLE (movie_id text, title text, poster text, year text, added_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT f.movie_id::text, f.title::text, f.poster::text, f.year::text, f.added_at AT TIME ZONE 'utc'
    FROM favorite f
    WHERE f.user_id = p_user_id AND f.status
      AND (p_cursor_ts IS NULL OR (f.added_at AT TIME ZONE 'utc', f.movie_id::text) < (p_cursor_ts, p_cursor_id))
    ORDER BY f.added_at DESC, f.movie_id DESC
    LIMIT p_limit;
$$;

-- Idempotente: devuelve created=false si ya existía
CREATE OR REPLACE FUNCTION api.favorite_add(
    p_user_id uuid, p_movie_id text, p_title text, p_poster text, p_year text
)
RETURNS TABLE (created boolean, movie_id text, title text, poster text, year text, added_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_created boolean := false;
BEGIN
    -- Serializa por usuario+película para no duplicar (la tabla heredada no tiene índice único)
    PERFORM pg_advisory_xact_lock(hashtext('favorite:' || p_user_id::text || ':' || p_movie_id));
    IF NOT EXISTS (SELECT 1 FROM favorite f WHERE f.user_id = p_user_id AND f.movie_id = p_movie_id) THEN
        INSERT INTO favorite (id, user_id, movie_id, title, poster, year, added_at, status)
        VALUES (gen_random_uuid(), p_user_id, p_movie_id, p_title, p_poster, p_year, now() AT TIME ZONE 'utc', true);
        v_created := true;
    ELSE
        UPDATE favorite f SET status = true WHERE f.user_id = p_user_id AND f.movie_id = p_movie_id;
    END IF;

    RETURN QUERY
    SELECT v_created, f.movie_id::text, f.title::text, f.poster::text, f.year::text, f.added_at AT TIME ZONE 'utc'
    FROM favorite f WHERE f.user_id = p_user_id AND f.movie_id = p_movie_id
    ORDER BY f.added_at LIMIT 1;
END
$$;

CREATE OR REPLACE FUNCTION api.favorite_remove(p_user_id uuid, p_movie_id text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    DELETE FROM favorite f WHERE f.user_id = p_user_id AND f.movie_id = p_movie_id;
$$;

-- =====================================================================
-- Personas favoritas
-- =====================================================================

CREATE OR REPLACE FUNCTION api.favorite_person_list(
    p_user_id uuid, p_cursor_ts timestamptz, p_cursor_id text, p_limit integer
)
RETURNS TABLE (person_id text, name text, photo text, job text, known_for text, created_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT fp.person_id::text, fp.name::text, fp.photo::text, fp.job::text, fp.known_for::text,
           fp.created_at AT TIME ZONE 'utc'
    FROM favoriteperson fp
    WHERE fp.user_id = p_user_id
      AND (p_cursor_ts IS NULL OR (fp.created_at AT TIME ZONE 'utc', fp.person_id::text) < (p_cursor_ts, p_cursor_id))
    ORDER BY fp.created_at DESC, fp.person_id DESC
    LIMIT p_limit;
$$;

CREATE OR REPLACE FUNCTION api.favorite_person_add(
    p_user_id uuid, p_person_id text, p_name text, p_photo text, p_job text, p_known_for text
)
RETURNS TABLE (created boolean, person_id text, name text, photo text, job text, known_for text, created_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_created boolean := false;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('person:' || p_user_id::text || ':' || p_person_id));
    IF NOT EXISTS (SELECT 1 FROM favoriteperson fp WHERE fp.user_id = p_user_id AND fp.person_id = p_person_id) THEN
        INSERT INTO favoriteperson (id, user_id, person_id, name, photo, job, known_for, created_at)
        VALUES (gen_random_uuid(), p_user_id, p_person_id, p_name, p_photo, p_job, p_known_for, now() AT TIME ZONE 'utc');
        v_created := true;
    END IF;

    RETURN QUERY
    SELECT v_created, fp.person_id::text, fp.name::text, fp.photo::text, fp.job::text, fp.known_for::text,
           fp.created_at AT TIME ZONE 'utc'
    FROM favoriteperson fp WHERE fp.user_id = p_user_id AND fp.person_id = p_person_id
    ORDER BY fp.created_at LIMIT 1;
END
$$;

CREATE OR REPLACE FUNCTION api.favorite_person_remove(p_user_id uuid, p_person_id text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    DELETE FROM favoriteperson fp WHERE fp.user_id = p_user_id AND fp.person_id = p_person_id;
$$;

-- =====================================================================
-- Ver después / Vistas
-- =====================================================================

CREATE OR REPLACE FUNCTION api.watchlist_list(
    p_user_id uuid, p_cursor_ts timestamptz, p_cursor_id text, p_limit integer
)
RETURNS TABLE (movie_id text, title text, poster text, year text, added_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT w.movie_id::text, w.title::text, w.poster::text, w.year::text, w.added_at
    FROM watchlist_item w
    WHERE w.user_id = p_user_id
      AND (p_cursor_ts IS NULL OR (w.added_at, w.movie_id::text) < (p_cursor_ts, p_cursor_id))
    ORDER BY w.added_at DESC, w.movie_id DESC
    LIMIT p_limit;
$$;

CREATE OR REPLACE FUNCTION api.watchlist_add(
    p_user_id uuid, p_movie_id text, p_title text, p_poster text, p_year text
)
RETURNS TABLE (created boolean, movie_id text, title text, poster text, year text, added_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_created boolean;
BEGIN
    INSERT INTO watchlist_item (user_id, movie_id, title, poster, year)
    VALUES (p_user_id, p_movie_id, p_title, p_poster, p_year)
    ON CONFLICT (user_id, movie_id) DO NOTHING;
    v_created := FOUND;

    RETURN QUERY
    SELECT v_created, w.movie_id::text, w.title::text, w.poster::text, w.year::text, w.added_at
    FROM watchlist_item w WHERE w.user_id = p_user_id AND w.movie_id = p_movie_id;
END
$$;

CREATE OR REPLACE FUNCTION api.watchlist_remove(p_user_id uuid, p_movie_id text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    DELETE FROM watchlist_item w WHERE w.user_id = p_user_id AND w.movie_id = p_movie_id;
$$;

CREATE OR REPLACE FUNCTION api.watched_list(
    p_user_id uuid, p_cursor_ts timestamptz, p_cursor_id text, p_limit integer
)
RETURNS TABLE (movie_id text, title text, poster text, year text, watched_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT w.movie_id::text, w.title::text, w.poster::text, w.year::text, w.watched_at
    FROM watched_item w
    WHERE w.user_id = p_user_id
      AND (p_cursor_ts IS NULL OR (w.watched_at, w.movie_id::text) < (p_cursor_ts, p_cursor_id))
    ORDER BY w.watched_at DESC, w.movie_id DESC
    LIMIT p_limit;
$$;

-- Marca como vista (o actualiza la fecha) y la saca de "ver después"
CREATE OR REPLACE FUNCTION api.watched_add(
    p_user_id uuid, p_movie_id text, p_title text, p_poster text, p_year text, p_watched_at timestamptz
)
RETURNS TABLE (created boolean, movie_id text, title text, poster text, year text, watched_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_created boolean;
BEGIN
    v_created := NOT EXISTS (SELECT 1 FROM watched_item w WHERE w.user_id = p_user_id AND w.movie_id = p_movie_id);
    INSERT INTO watched_item (user_id, movie_id, title, poster, year, watched_at)
    VALUES (p_user_id, p_movie_id, p_title, p_poster, p_year, coalesce(p_watched_at, now()))
    ON CONFLICT (user_id, movie_id) DO UPDATE
        SET watched_at = coalesce(p_watched_at, watched_item.watched_at);

    DELETE FROM watchlist_item w WHERE w.user_id = p_user_id AND w.movie_id = p_movie_id;

    RETURN QUERY
    SELECT v_created, w.movie_id::text, w.title::text, w.poster::text, w.year::text, w.watched_at
    FROM watched_item w WHERE w.user_id = p_user_id AND w.movie_id = p_movie_id;
END
$$;

CREATE OR REPLACE FUNCTION api.watched_remove(p_user_id uuid, p_movie_id text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    DELETE FROM watched_item w WHERE w.user_id = p_user_id AND w.movie_id = p_movie_id;
$$;

-- =====================================================================
-- Listas personalizadas
-- =====================================================================

CREATE OR REPLACE FUNCTION api.list_all(p_user_id uuid)
RETURNS TABLE (id uuid, name text, description text, is_public boolean, item_count bigint,
               created_at timestamptz, updated_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT l.id, l.name::text, l.description::text, l.is_public,
           (SELECT count(*) FROM user_list_item i WHERE i.list_id = l.id), l.created_at, l.updated_at
    FROM user_list l
    WHERE l.user_id = p_user_id
    ORDER BY l.updated_at DESC;
$$;

-- Lista visible para p_viewer_id (dueño, o cualquiera si es pública)
CREATE OR REPLACE FUNCTION api.list_get(p_viewer_id uuid, p_list_id uuid)
RETURNS TABLE (id uuid, owner_username text, is_owner boolean, name text, description text,
               is_public boolean, item_count bigint, created_at timestamptz, updated_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT l.id, u.username::text, l.user_id = p_viewer_id, l.name::text, l.description::text, l.is_public,
           (SELECT count(*) FROM user_list_item i WHERE i.list_id = l.id), l.created_at, l.updated_at
    FROM user_list l
    JOIN "user" u ON u.id = l.user_id
    WHERE l.id = p_list_id
      AND (l.user_id = p_viewer_id OR (l.is_public AND u.account_status = 'active' AND u.status));
$$;

-- Estados: ok | limit_reached | name_taken
CREATE OR REPLACE FUNCTION api.list_create(
    p_user_id uuid, p_name text, p_description text, p_is_public boolean, p_max_lists integer
)
RETURNS TABLE (status text, list_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_id uuid;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('lists:' || p_user_id::text));
    IF (SELECT count(*) FROM user_list l WHERE l.user_id = p_user_id) >= p_max_lists THEN
        RETURN QUERY SELECT 'limit_reached'::text, NULL::uuid; RETURN;
    END IF;
    BEGIN
        INSERT INTO user_list (user_id, name, description, is_public)
        VALUES (p_user_id, p_name, p_description, coalesce(p_is_public, false))
        RETURNING user_list.id INTO v_id;
    EXCEPTION WHEN unique_violation THEN
        RETURN QUERY SELECT 'name_taken'::text, NULL::uuid; RETURN;
    END;
    RETURN QUERY SELECT 'ok'::text, v_id;
END
$$;

-- Estados: ok | not_found | name_taken
CREATE OR REPLACE FUNCTION api.list_update(
    p_user_id uuid, p_list_id uuid, p_name text, p_set_description boolean, p_description text,
    p_is_public boolean
)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE user_list l
    SET name = coalesce(p_name, l.name),
        description = CASE WHEN p_set_description THEN p_description ELSE l.description END,
        is_public = coalesce(p_is_public, l.is_public),
        updated_at = now()
    WHERE l.id = p_list_id AND l.user_id = p_user_id;
    IF NOT FOUND THEN
        RETURN 'not_found';
    END IF;
    RETURN 'ok';
EXCEPTION WHEN unique_violation THEN
    RETURN 'name_taken';
END
$$;

CREATE OR REPLACE FUNCTION api.list_delete(p_user_id uuid, p_list_id uuid)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    DELETE FROM user_list l WHERE l.id = p_list_id AND l.user_id = p_user_id;
    RETURN FOUND;
END
$$;

CREATE OR REPLACE FUNCTION api.list_items(
    p_list_id uuid, p_cursor_ts timestamptz, p_cursor_id text, p_limit integer
)
RETURNS TABLE (movie_id text, title text, poster text, year text, added_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT i.movie_id::text, i.title::text, i.poster::text, i.year::text, i.added_at
    FROM user_list_item i
    WHERE i.list_id = p_list_id
      AND (p_cursor_ts IS NULL OR (i.added_at, i.movie_id::text) < (p_cursor_ts, p_cursor_id))
    ORDER BY i.added_at DESC, i.movie_id DESC
    LIMIT p_limit;
$$;

-- Estados: ok | exists | not_found | limit_reached
CREATE OR REPLACE FUNCTION api.list_item_add(
    p_user_id uuid, p_list_id uuid, p_movie_id text, p_title text, p_poster text, p_year text,
    p_max_items integer
)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    PERFORM 1 FROM user_list l WHERE l.id = p_list_id AND l.user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN 'not_found';
    END IF;
    IF EXISTS (SELECT 1 FROM user_list_item i WHERE i.list_id = p_list_id AND i.movie_id = p_movie_id) THEN
        RETURN 'exists';
    END IF;
    IF (SELECT count(*) FROM user_list_item i WHERE i.list_id = p_list_id) >= p_max_items THEN
        RETURN 'limit_reached';
    END IF;
    INSERT INTO user_list_item (list_id, movie_id, title, poster, year)
    VALUES (p_list_id, p_movie_id, p_title, p_poster, p_year);
    UPDATE user_list l SET updated_at = now() WHERE l.id = p_list_id;
    RETURN 'ok';
END
$$;

-- Estados: ok | not_found (lista ajena o inexistente)
CREATE OR REPLACE FUNCTION api.list_item_remove(p_user_id uuid, p_list_id uuid, p_movie_id text)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    PERFORM 1 FROM user_list l WHERE l.id = p_list_id AND l.user_id = p_user_id;
    IF NOT FOUND THEN
        RETURN 'not_found';
    END IF;
    DELETE FROM user_list_item i WHERE i.list_id = p_list_id AND i.movie_id = p_movie_id;
    IF FOUND THEN
        UPDATE user_list l SET updated_at = now() WHERE l.id = p_list_id;
    END IF;
    RETURN 'ok';
END
$$;

-- =====================================================================
-- Reseñas
-- =====================================================================

-- Forma común de una reseña (las de cuentas dadas de baja no se muestran a otros)
CREATE OR REPLACE FUNCTION api.review_list_by_movie(
    p_movie_id text, p_cursor_ts timestamptz, p_cursor_id text, p_limit integer
)
RETURNS TABLE (id uuid, user_id uuid, username text, movie_id text, movie_title text, movie_poster text,
               rating integer, content text, sentiment text, created_at timestamptz, updated_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT r.id, r.user_id, u.username::text, r.movie_id::text, m.title::text, m.poster::text,
           r.rating, r.content::text, r.sentiment::text,
           r.created_at AT TIME ZONE 'utc', r.updated_at AT TIME ZONE 'utc'
    FROM review r
    JOIN "user" u ON u.id = r.user_id
    LEFT JOIN movie m ON m.id = r.movie_id
    WHERE r.movie_id = p_movie_id AND u.account_status = 'active' AND u.status
      AND (p_cursor_ts IS NULL OR (r.created_at AT TIME ZONE 'utc', r.id::text) < (p_cursor_ts, p_cursor_id))
    ORDER BY r.created_at DESC, r.id DESC
    LIMIT p_limit;
$$;

CREATE OR REPLACE FUNCTION api.review_movie_summary(p_movie_id text)
RETURNS TABLE (review_count bigint, avg_rating numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT count(*), round(avg(r.rating)::numeric, 2)
    FROM review r JOIN "user" u ON u.id = r.user_id
    WHERE r.movie_id = p_movie_id AND u.account_status = 'active' AND u.status;
$$;

CREATE OR REPLACE FUNCTION api.review_list_by_user(
    p_user_id uuid, p_cursor_ts timestamptz, p_cursor_id text, p_limit integer
)
RETURNS TABLE (id uuid, user_id uuid, username text, movie_id text, movie_title text, movie_poster text,
               rating integer, content text, sentiment text, created_at timestamptz, updated_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT r.id, r.user_id, u.username::text, r.movie_id::text, m.title::text, m.poster::text,
           r.rating, r.content::text, r.sentiment::text,
           r.created_at AT TIME ZONE 'utc', r.updated_at AT TIME ZONE 'utc'
    FROM review r
    JOIN "user" u ON u.id = r.user_id
    LEFT JOIN movie m ON m.id = r.movie_id
    WHERE r.user_id = p_user_id
      AND (p_cursor_ts IS NULL OR (r.created_at AT TIME ZONE 'utc', r.id::text) < (p_cursor_ts, p_cursor_id))
    ORDER BY r.created_at DESC, r.id DESC
    LIMIT p_limit;
$$;

CREATE OR REPLACE FUNCTION api.review_get(p_review_id uuid)
RETURNS TABLE (id uuid, user_id uuid, username text, movie_id text, movie_title text, movie_poster text,
               rating integer, content text, sentiment text, created_at timestamptz, updated_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT r.id, r.user_id, u.username::text, r.movie_id::text, m.title::text, m.poster::text,
           r.rating, r.content::text, r.sentiment::text,
           r.created_at AT TIME ZONE 'utc', r.updated_at AT TIME ZONE 'utc'
    FROM review r
    JOIN "user" u ON u.id = r.user_id
    LEFT JOIN movie m ON m.id = r.movie_id
    WHERE r.id = p_review_id;
$$;

CREATE OR REPLACE FUNCTION api._sentiment(p_rating integer)
RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp
AS $$
    SELECT CASE WHEN p_rating >= 4 THEN 'positive' WHEN p_rating = 3 THEN 'neutral' ELSE 'negative' END;
$$;

-- Estados: ok | exists
CREATE OR REPLACE FUNCTION api.review_create(
    p_user_id uuid, p_movie_id text, p_movie_title text, p_movie_poster text, p_movie_year text,
    p_rating integer, p_content text
)
RETURNS TABLE (status text, review_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_id uuid;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('review:' || p_user_id::text || ':' || p_movie_id));
    IF EXISTS (SELECT 1 FROM review r WHERE r.user_id = p_user_id AND r.movie_id = p_movie_id) THEN
        RETURN QUERY SELECT 'exists'::text, NULL::uuid; RETURN;
    END IF;

    INSERT INTO movie (id, title, poster, year, vote_count, vote_sum)
    VALUES (p_movie_id, p_movie_title, coalesce(p_movie_poster, ''), coalesce(p_movie_year, 'N/A'), 0, 0)
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO review (id, user_id, movie_id, rating, content, sentiment, created_at, updated_at)
    VALUES (gen_random_uuid(), p_user_id, p_movie_id, p_rating, p_content, api._sentiment(p_rating),
            now() AT TIME ZONE 'utc', now() AT TIME ZONE 'utc')
    RETURNING review.id INTO v_id;

    RETURN QUERY SELECT 'ok'::text, v_id;
END
$$;

-- Estados: ok | not_found | forbidden
CREATE OR REPLACE FUNCTION api.review_update(
    p_user_id uuid, p_review_id uuid, p_rating integer, p_content text
)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_owner uuid;
BEGIN
    SELECT r.user_id INTO v_owner FROM review r WHERE r.id = p_review_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN 'not_found';
    END IF;
    IF v_owner <> p_user_id THEN
        RETURN 'forbidden';
    END IF;
    UPDATE review r
    SET rating = coalesce(p_rating, r.rating),
        sentiment = api._sentiment(coalesce(p_rating, r.rating)),
        content = coalesce(p_content, r.content),
        updated_at = now() AT TIME ZONE 'utc'
    WHERE r.id = p_review_id;
    RETURN 'ok';
END
$$;

-- Estados: ok | not_found | forbidden
CREATE OR REPLACE FUNCTION api.review_delete(p_user_id uuid, p_review_id uuid)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_owner uuid;
BEGIN
    SELECT r.user_id INTO v_owner FROM review r WHERE r.id = p_review_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN 'not_found';
    END IF;
    IF v_owner <> p_user_id THEN
        RETURN 'forbidden';
    END IF;
    DELETE FROM review r WHERE r.id = p_review_id;
    RETURN 'ok';
END
$$;

-- =====================================================================
-- Estado de una película para el usuario (botones de la ficha en 1 llamada)
-- =====================================================================
CREATE OR REPLACE FUNCTION api.movie_state(p_user_id uuid, p_movie_id text)
RETURNS TABLE (is_favorite boolean, in_watchlist boolean, watched_at timestamptz,
               review_id uuid, in_lists uuid[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT
        EXISTS (SELECT 1 FROM favorite f WHERE f.user_id = p_user_id AND f.movie_id = p_movie_id AND f.status),
        EXISTS (SELECT 1 FROM watchlist_item w WHERE w.user_id = p_user_id AND w.movie_id = p_movie_id),
        (SELECT w.watched_at FROM watched_item w WHERE w.user_id = p_user_id AND w.movie_id = p_movie_id),
        (SELECT r.id FROM review r WHERE r.user_id = p_user_id AND r.movie_id = p_movie_id LIMIT 1),
        coalesce((SELECT array_agg(i.list_id ORDER BY i.list_id)
                  FROM user_list_item i JOIN user_list l ON l.id = i.list_id
                  WHERE l.user_id = p_user_id AND i.movie_id = p_movie_id), '{}'::uuid[]);
$$;

-- Permisos explícitos
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA api FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA api TO movie_api_runtime;
REVOKE EXECUTE ON FUNCTION api._consume_code(text, text, bytea, integer) FROM movie_api_runtime;
REVOKE EXECUTE ON FUNCTION api._sentiment(integer) FROM movie_api_runtime;
