-- Create missing tables for enhanced state management system
-- Created as part of security audit implementation

begin;

-- Create game_states table for Redis/Database hybrid state management
create table if not exists public.game_states (
    id uuid default gen_random_uuid() primary key,
    game_id varchar(255) not null unique,
    state_data jsonb not null,
    state_version integer default 1,
    last_activity timestamp with time zone default now(),
    ttl_seconds integer default 86400,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- Create indexes for game_states
create index if not exists idx_game_states_game_id on public.game_states(game_id);
create index if not exists idx_game_states_last_activity on public.game_states(last_activity);
create index if not exists idx_game_states_created_at on public.game_states(created_at);

-- Create saved_games table for game persistence
create table if not exists public.saved_games (
    id uuid default gen_random_uuid() primary key,
    user_id uuid references public.users(id) on delete cascade,
    game_name varchar(255) not null,
    filename varchar(500) not null,
    game_data jsonb not null,
    description text,
    tags text[],
    is_public boolean default false,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- Create indexes for saved_games
create index if not exists idx_saved_games_user_id on public.saved_games(user_id);
create index if not exists idx_saved_games_filename on public.saved_games(filename);
create index if not exists idx_saved_games_created_at on public.saved_games(created_at);
create index if not exists idx_saved_games_is_public on public.saved_games(is_public);

-- Create user_preferences table for user settings
create table if not exists public.user_preferences (
    id uuid default gen_random_uuid() primary key,
    user_id uuid references public.users(id) on delete cascade unique,
    preferences jsonb not null default '{}',
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- Create index for user_preferences
create index if not exists idx_user_preferences_user_id on public.user_preferences(user_id);

-- Create state_migrations table for tracking data migrations
create table if not exists public.state_migrations (
    id uuid default gen_random_uuid() primary key,
    migration_id varchar(255) not null unique,
    migration_type varchar(100) not null,
    source_data jsonb,
    target_data jsonb,
    status varchar(50) default 'pending',
    error_message text,
    created_at timestamp with time zone default now(),
    completed_at timestamp with time zone
);

-- Create indexes for state_migrations
create index if not exists idx_state_migrations_migration_id on public.state_migrations(migration_id);
create index if not exists idx_state_migrations_status on public.state_migrations(status);
create index if not exists idx_state_migrations_created_at on public.state_migrations(created_at);

-- Create function to test if table exists (for health checks)
create or replace function public.test_table_exists(table_name text)
returns boolean
language plpgsql
security definer
as $$
begin
    return exists (
        select 1 
        from information_schema.tables 
        where table_schema = 'public' 
        and table_name = $1
    );
end;
$$;

-- Create updated_at trigger function if it doesn't exist
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- Create updated_at triggers for new tables (drop first to ensure idempotency)
drop trigger if exists set_game_states_updated_at on public.game_states;
create trigger set_game_states_updated_at
    before update on public.game_states
    for each row execute function public.set_updated_at();

drop trigger if exists set_saved_games_updated_at on public.saved_games;
create trigger set_saved_games_updated_at
    before update on public.saved_games
    for each row execute function public.set_updated_at();

drop trigger if exists set_user_preferences_updated_at on public.user_preferences;
create trigger set_user_preferences_updated_at
    before update on public.user_preferences
    for each row execute function public.set_updated_at();

-- RLS (Row Level Security) policies for game_states
alter table public.game_states enable row level security;

create policy if not exists "game_states_select"
on public.game_states
for select
to public
using (
  exists (
    select 1 from public.games g
    where g.id::text = public.game_states.game_id
    and (
      g.host_id = (select auth.uid())
      or exists (
        select 1 from public.game_players gp
        where gp.game_id = g.id
        and gp.user_id = (select auth.uid())
      )
    )
  )
);

create policy if not exists "game_states_insert"
on public.game_states
for insert
to authenticated
with check (
  exists (
    select 1 from public.games g
    where g.id::text = public.game_states.game_id
    and g.host_id = (select auth.uid())
  )
);

create policy if not exists "game_states_update"
on public.game_states
for update
to authenticated
using (
  exists (
    select 1 from public.games g
    where g.id::text = public.game_states.game_id
    and g.host_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1 from public.games g
    where g.id::text = public.game_states.game_id
    and g.host_id = (select auth.uid())
  )
);

create policy if not exists "game_states_delete"
on public.game_states
for delete
to authenticated
using (
  exists (
    select 1 from public.games g
    where g.id::text = public.game_states.game_id
    and g.host_id = (select auth.uid())
  )
);

-- RLS policies for saved_games
alter table public.saved_games enable row level security;

create policy if not exists "saved_games_select"
on public.saved_games
for select
to public
using (
  user_id = (select auth.uid()) or is_public = true
);

create policy if not exists "saved_games_insert_own"
on public.saved_games
for insert
to authenticated
with check (user_id = (select auth.uid()));

create policy if not exists "saved_games_update_own"
on public.saved_games
for update
to authenticated
using (user_id = (select auth.uid()))
with check (user_id = (select auth.uid()));

create policy if not exists "saved_games_delete_own"
on public.saved_games
for delete
to authenticated
using (user_id = (select auth.uid()));

-- RLS policies for user_preferences
alter table public.user_preferences enable row level security;

create policy if not exists "user_preferences_select_own"
on public.user_preferences
for select
to authenticated
using (user_id = (select auth.uid()));

create policy if not exists "user_preferences_insert_own"
on public.user_preferences
for insert
to authenticated
with check (user_id = (select auth.uid()));

create policy if not exists "user_preferences_update_own"
on public.user_preferences
for update
to authenticated
using (user_id = (select auth.uid()))
with check (user_id = (select auth.uid()));

create policy if not exists "user_preferences_delete_own"
on public.user_preferences
for delete
to authenticated
using (user_id = (select auth.uid()));

-- RLS policies for state_migrations (admin/service only)
alter table public.state_migrations enable row level security;

create policy if not exists "state_migrations_service_only"
on public.state_migrations
for all
to service_role
using (true)
with check (true);

commit;