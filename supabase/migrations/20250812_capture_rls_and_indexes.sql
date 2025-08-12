begin;

-- RLS policy consolidation and initplan fixes
-- games
drop policy if exists "Game hosts can manage games" on public.games;
drop policy if exists "Users can view games they're in" on public.games;

create policy if not exists "games_select"
on public.games
for select
to public
using (
  host_id = (select auth.uid())
  or exists (
    select 1 from public.game_players gp
    where gp.game_id = public.games.id
      and gp.user_id = (select auth.uid())
  )
);

create policy if not exists "games_insert_own"
on public.games
for insert
to authenticated
with check (host_id = (select auth.uid()));

create policy if not exists "games_update_own"
on public.games
for update
to authenticated
using (host_id = (select auth.uid()))
with check (host_id = (select auth.uid()));

create policy if not exists "games_delete_own"
on public.games
for delete
to authenticated
using (host_id = (select auth.uid()));

-- bingo_cards
drop policy if exists "Users can manage own bingo cards" on public.bingo_cards;
drop policy if exists "Users can view bingo cards in their games" on public.bingo_cards;

create policy if not exists "bingo_cards_select"
on public.bingo_cards
for select
to public
using (
  user_id = (select auth.uid())
  or exists (
    select 1 from public.game_players gp
    where gp.game_id = public.bingo_cards.game_id
      and gp.user_id = (select auth.uid())
  )
);

create policy if not exists "bingo_cards_insert_own"
on public.bingo_cards
for insert
to authenticated
with check (user_id = (select auth.uid()));

create policy if not exists "bingo_cards_update_own"
on public.bingo_cards
for update
to authenticated
using (user_id = (select auth.uid()))
with check (user_id = (select auth.uid()));

create policy if not exists "bingo_cards_delete_own"
on public.bingo_cards
for delete
to authenticated
using (user_id = (select auth.uid()));

-- game_players
drop policy if exists "Users can manage their own game participation" on public.game_players;
drop policy if exists "Users can view game players in their games" on public.game_players;

create policy if not exists "game_players_select"
on public.game_players
for select
to public
using (
  exists (
    select 1 from public.game_players gp_self
    where gp_self.game_id = public.game_players.game_id
      and gp_self.user_id = (select auth.uid())
  )
);

create policy if not exists "game_players_insert_own"
on public.game_players
for insert
to authenticated
with check (user_id = (select auth.uid()));

create policy if not exists "game_players_update_own"
on public.game_players
for update
to authenticated
using (user_id = (select auth.uid()))
with check (user_id = (select auth.uid()));

create policy if not exists "game_players_delete_own"
on public.game_players
for delete
to authenticated
using (user_id = (select auth.uid()));

-- playlists
drop policy if exists "Users can manage own playlists" on public.playlists;
drop policy if exists "Users can view public playlists" on public.playlists;

create policy if not exists "playlists_select"
on public.playlists
for select
to public
using (
  is_public = true or owner_id = (select auth.uid())
);

create policy if not exists "playlists_insert_own"
on public.playlists
for insert
to authenticated
with check (owner_id = (select auth.uid()));

create policy if not exists "playlists_update_own"
on public.playlists
for update
to authenticated
using (owner_id = (select auth.uid()))
with check (owner_id = (select auth.uid()));

create policy if not exists "playlists_delete_own"
on public.playlists
for delete
to authenticated
using (owner_id = (select auth.uid()));

-- chat_messages
alter policy "Users can post chat in their games" on public.chat_messages
with check (
  exists (
    select 1 from public.game_players gp
    where gp.game_id = public.chat_messages.game_id
      and gp.user_id = (select auth.uid())
  )
);

alter policy "Users can view chat in their games" on public.chat_messages
using (
  exists (
    select 1 from public.game_players gp
    where gp.game_id = public.chat_messages.game_id
      and gp.user_id = (select auth.uid())
  )
);

-- users
alter policy "Users can view own profile" on public.users
using (id = (select auth.uid()));

alter policy "Users can update own profile" on public.users
using (id = (select auth.uid()))
with check (id = (select auth.uid()));

-- subscriptions
alter policy "Users can view own subscriptions" on public.subscriptions
using (user_id = (select auth.uid()));

-- user_sessions
alter policy "Users can view own sessions" on public.user_sessions
using (user_id = (select auth.uid()))
with check (user_id = (select auth.uid()));

-- game_events
alter policy "Users can view events in their games" on public.game_events
using (
  exists (
    select 1 from public.game_players gp
    where gp.game_id = public.game_events.game_id
      and gp.user_id = (select auth.uid())
  )
);

-- Index changes: add covering FK indexes (idempotent)
create index if not exists idx_chat_messages_user_id on public.chat_messages(user_id);
create index if not exists idx_game_events_user_id on public.game_events(user_id);
create index if not exists idx_games_winner_id on public.games(winner_id);

-- Remove redundant/duplicate indexes if they exist
drop index if exists public.idx_game_players_game_user;
drop index if exists public.idx_game_players_game_id;
drop index if exists public.idx_bingo_cards_game_id;
drop index if exists public.idx_chat_messages_game_id;
drop index if exists public.idx_game_events_game_id;
drop index if exists public.idx_users_email;
drop index if exists public.idx_users_spotify_id;
drop index if exists public.idx_subscriptions_stripe_subscription_id;
drop index if exists public.idx_user_sessions_session_token;

commit;


