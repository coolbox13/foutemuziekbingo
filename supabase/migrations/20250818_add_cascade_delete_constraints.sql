-- CRIT-002 Fix: Add CASCADE DELETE to existing foreign key constraints
-- This migration ensures orphaned records are automatically cleaned up when parent records are deleted
-- Created: 2025-08-18
-- Issue: CRIT-002 - Database Orphaned Records

begin;

-- Log migration start
insert into public.state_migrations (migration_id, migration_type, status, created_at)
values ('20250818_cascade_delete', 'constraint_update', 'in_progress', now());

-- 1. DROP existing foreign key constraints (if they exist without CASCADE)
-- Note: These constraints were likely created in previous migrations without CASCADE DELETE

-- Drop game_players constraints
alter table public.game_players 
drop constraint if exists game_players_game_id_fkey;

alter table public.game_players 
drop constraint if exists game_players_user_id_fkey;

-- Drop bingo_cards constraints  
alter table public.bingo_cards 
drop constraint if exists bingo_cards_game_id_fkey;

alter table public.bingo_cards 
drop constraint if exists bingo_cards_user_id_fkey;

-- Drop any other related constraints
alter table public.games 
drop constraint if exists games_host_id_fkey;

alter table public.games 
drop constraint if exists games_playlist_id_fkey;

-- 2. RE-CREATE foreign key constraints WITH CASCADE DELETE

-- game_players constraints with CASCADE DELETE
alter table public.game_players 
add constraint game_players_game_id_fkey 
foreign key (game_id) references public.games(id) on delete cascade;

alter table public.game_players 
add constraint game_players_user_id_fkey 
foreign key (user_id) references public.users(id) on delete cascade;

-- bingo_cards constraints with CASCADE DELETE
alter table public.bingo_cards 
add constraint bingo_cards_game_id_fkey 
foreign key (game_id) references public.games(id) on delete cascade;

alter table public.bingo_cards 
add constraint bingo_cards_user_id_fkey 
foreign key (user_id) references public.users(id) on delete cascade;

-- games constraints (these should be RESTRICT or SET NULL, not CASCADE)
alter table public.games 
add constraint games_host_id_fkey 
foreign key (host_id) references public.users(id) on delete restrict;

alter table public.games 
add constraint games_playlist_id_fkey 
foreign key (playlist_id) references public.playlists(id) on delete restrict;

-- 3. Add performance indexes for foreign key columns (if not already present)
create index if not exists idx_game_players_game_id on public.game_players(game_id);
create index if not exists idx_game_players_user_id on public.game_players(user_id);
create index if not exists idx_bingo_cards_game_id on public.bingo_cards(game_id);
create index if not exists idx_bingo_cards_user_id on public.bingo_cards(user_id);
create index if not exists idx_games_host_id on public.games(host_id);
create index if not exists idx_games_playlist_id on public.games(playlist_id);

-- 4. Create data integrity validation function
create or replace function public.validate_referential_integrity()
returns table(
    table_name text,
    constraint_name text,
    validation_status text,
    orphaned_count integer
)
language plpgsql
security definer
as $$
begin
    -- Validate game_players → games relationship
    return query
    select 
        'game_players'::text as table_name,
        'game_players_game_id_fkey'::text as constraint_name,
        case 
            when count(*) = 0 then 'VALID'::text
            else 'ORPHANED_RECORDS'::text
        end as validation_status,
        count(*)::integer as orphaned_count
    from public.game_players gp
    left join public.games g on gp.game_id = g.id
    where g.id is null;
    
    -- Validate bingo_cards → games relationship
    return query
    select 
        'bingo_cards'::text as table_name,
        'bingo_cards_game_id_fkey'::text as constraint_name,
        case 
            when count(*) = 0 then 'VALID'::text
            else 'ORPHANED_RECORDS'::text
        end as validation_status,
        count(*)::integer as orphaned_count
    from public.bingo_cards bc
    left join public.games g on bc.game_id = g.id
    where g.id is null;
    
    -- Validate game_players → users relationship
    return query
    select 
        'game_players'::text as table_name,
        'game_players_user_id_fkey'::text as constraint_name,
        case 
            when count(*) = 0 then 'VALID'::text
            else 'ORPHANED_RECORDS'::text
        end as validation_status,
        count(*)::integer as orphaned_count
    from public.game_players gp
    left join public.users u on gp.user_id = u.id
    where u.id is null;
    
    -- Validate bingo_cards → users relationship  
    return query
    select 
        'bingo_cards'::text as table_name,
        'bingo_cards_user_id_fkey'::text as constraint_name,
        case 
            when count(*) = 0 then 'VALID'::text
            else 'ORPHANED_RECORDS'::text
        end as validation_status,
        count(*)::integer as orphaned_count
    from public.bingo_cards bc
    left join public.users u on bc.user_id = u.id
    where u.id is null;
end;
$$;

-- Grant execute permission on validation function
grant execute on function public.validate_referential_integrity() to authenticated;

-- 5. Run validation to ensure migration success
do $$
declare
    validation_result record;
    has_orphaned_records boolean := false;
begin
    -- Check validation results
    for validation_result in 
        select * from public.validate_referential_integrity()
    loop
        if validation_result.orphaned_count > 0 then
            has_orphaned_records := true;
            raise warning 'VALIDATION WARNING: Table % has % orphaned records for constraint %',
                validation_result.table_name,
                validation_result.orphaned_count,
                validation_result.constraint_name;
        end if;
    end loop;
    
    -- If no orphaned records, migration is successful
    if not has_orphaned_records then
        raise notice 'VALIDATION SUCCESS: All referential integrity constraints are valid';
        
        -- Update migration status to completed
        update public.state_migrations 
        set status = 'completed', completed_at = now()
        where migration_id = '20250818_cascade_delete';
    else
        raise exception 'MIGRATION FAILED: Orphaned records detected. Manual cleanup required before applying CASCADE constraints.';
    end if;
end;
$$;

-- 6. Create monitoring view for ongoing integrity checks
create or replace view public.referential_integrity_status as
select 
    table_name,
    constraint_name,
    validation_status,
    orphaned_count,
    case 
        when validation_status = 'VALID' then '✅ HEALTHY'
        else '❌ NEEDS ATTENTION'
    end as status_emoji,
    now() as last_checked
from public.validate_referential_integrity();

-- Grant access to monitoring view
grant select on public.referential_integrity_status to authenticated;

commit;

-- Log successful completion
insert into public.state_migrations (migration_id, migration_type, status, completed_at)
values ('20250818_cascade_delete_success', 'constraint_update', 'completed', now())
on conflict (migration_id) do update set 
status = 'completed', 
completed_at = now();
