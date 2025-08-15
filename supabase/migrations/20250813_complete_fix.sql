-- Complete fix migration for Musical Bingo state management
-- Fixes all remaining issues: function parameters, missing columns, schema alignment

begin;

-- Fix the test_table_exists function to accept 'query' parameter as expected by app
drop function if exists public.test_table_exists(text);

create or replace function public.test_table_exists(query text)
returns boolean
language plpgsql
security definer
as $$
begin
    return exists (
        select 1 
        from information_schema.tables 
        where table_schema = 'public' 
        and table_name = query
    );
end;
$$;

-- Add missing columns to game_states table
alter table public.game_states 
add column if not exists created_by varchar(255),
add column if not exists description text,
add column if not exists state_type varchar(50) default 'snapshot',
add column if not exists is_checkpoint boolean default false,
add column if not exists is_final boolean default false;

-- Update game_states indexes
create index if not exists idx_game_states_created_by on public.game_states(created_by);
create index if not exists idx_game_states_state_type on public.game_states(state_type);
create index if not exists idx_game_states_is_checkpoint on public.game_states(is_checkpoint);

-- Ensure saved_games has all expected columns (add any missing)
alter table public.saved_games 
add column if not exists created_by varchar(255);

-- Update saved_games indexes  
create index if not exists idx_saved_games_created_by on public.saved_games(created_by);

-- Update RLS policies for game_states to handle created_by column
drop policy if exists "game_states_select" on public.game_states;
create policy "game_states_select"
on public.game_states
for select
to public
using (
  created_by = (select auth.uid()::text)
  or exists (
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

drop policy if exists "game_states_insert" on public.game_states;
create policy "game_states_insert"
on public.game_states
for insert
to authenticated
with check (
  created_by = (select auth.uid()::text)
  or exists (
    select 1 from public.games g
    where g.id::text = public.game_states.game_id
    and g.host_id = (select auth.uid())
  )
);

drop policy if exists "game_states_update" on public.game_states;
create policy "game_states_update"
on public.game_states
for update
to authenticated
using (
  created_by = (select auth.uid()::text)
  or exists (
    select 1 from public.games g
    where g.id::text = public.game_states.game_id
    and g.host_id = (select auth.uid())
  )
)
with check (
  created_by = (select auth.uid()::text)
  or exists (
    select 1 from public.games g
    where g.id::text = public.game_states.game_id
    and g.host_id = (select auth.uid())
  )
);

drop policy if exists "game_states_delete" on public.game_states;
create policy "game_states_delete"
on public.game_states
for delete
to authenticated
using (
  created_by = (select auth.uid()::text)
  or exists (
    select 1 from public.games g
    where g.id::text = public.game_states.game_id
    and g.host_id = (select auth.uid())
  )
);

-- Grant necessary permissions
grant usage on schema public to anon, authenticated;
grant all on public.game_states to anon, authenticated;
grant all on public.saved_games to anon, authenticated;
grant all on public.user_preferences to anon, authenticated;
grant all on public.state_migrations to anon, authenticated;
grant execute on function public.test_table_exists(text) to anon, authenticated;

commit;