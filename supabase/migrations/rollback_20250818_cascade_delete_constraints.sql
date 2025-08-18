-- ROLLBACK for 20250818_add_cascade_delete_constraints.sql
-- This script reverts CASCADE DELETE constraints back to RESTRICT/NO ACTION
-- Use only if CASCADE DELETE causes unexpected issues

begin;

-- Log rollback start
insert into public.state_migrations (migration_id, migration_type, status, created_at)
values ('20250818_cascade_delete_rollback', 'constraint_rollback', 'in_progress', now());

-- 1. DROP CASCADE DELETE constraints
alter table public.game_players 
drop constraint if exists game_players_game_id_fkey;

alter table public.game_players 
drop constraint if exists game_players_user_id_fkey;

alter table public.bingo_cards 
drop constraint if exists bingo_cards_game_id_fkey;

alter table public.bingo_cards 
drop constraint if exists bingo_cards_user_id_fkey;

alter table public.games 
drop constraint if exists games_host_id_fkey;

alter table public.games 
drop constraint if exists games_playlist_id_fkey;

-- 2. RE-CREATE constraints WITHOUT CASCADE (default behavior)
alter table public.game_players 
add constraint game_players_game_id_fkey 
foreign key (game_id) references public.games(id);

alter table public.game_players 
add constraint game_players_user_id_fkey 
foreign key (user_id) references public.users(id);

alter table public.bingo_cards 
add constraint bingo_cards_game_id_fkey 
foreign key (game_id) references public.games(id);

alter table public.bingo_cards 
add constraint bingo_cards_user_id_fkey 
foreign key (user_id) references public.users(id);

alter table public.games 
add constraint games_host_id_fkey 
foreign key (host_id) references public.users(id);

alter table public.games 
add constraint games_playlist_id_fkey 
foreign key (playlist_id) references public.playlists(id);

-- 3. Update migration status
update public.state_migrations 
set status = 'rolled_back', completed_at = now()
where migration_id = '20250818_cascade_delete';

insert into public.state_migrations (migration_id, migration_type, status, completed_at)
values ('20250818_cascade_delete_rollback', 'constraint_rollback', 'completed', now());

commit;

-- Note: After rollback, the emergency cleanup code in the application should be re-enabled
